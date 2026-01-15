//! # EAOS Userspace Network Stack
//!
//! A microkernel-style TCP/IP stack running in userspace for enhanced security.
//! This component isolates network operations from the kernel, communicating
//! with Organs via the Symbiote IPC layer.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────────────────────────┐
//! │                         USERSPACE                                │
//! │  ┌─────────┐    ┌─────────┐    ┌─────────────────────────────┐  │
//! │  │  Organ  │    │  Organ  │    │       Net-Stack Muscle      │  │
//! │  │ (Prism) │    │(Cardio) │    │  ┌─────────────────────────┐│  │
//! │  └────┬────┘    └────┬────┘    │  │    smoltcp Interface    ││  │
//! │       │              │         │  │  ┌─────────┐ ┌────────┐ ││  │
//! │       │              │         │  │  │ Sockets │ │ Routes │ ││  │
//! │       │              │         │  │  └─────────┘ └────────┘ ││  │
//! │       │              │         │  └─────────────────────────┘│  │
//! │       └──────┬───────┘         └──────────────┬──────────────┘  │
//! │              │                                │                  │
//! │       ┌──────▼──────────────────────────────▼─────┐             │
//! │       │              Symbiote IPC                  │             │
//! │       │         (SovereignBlob transport)         │             │
//! │       └──────────────────────────────────────────┘             │
//! └─────────────────────────────────────────────────────────────────┘
//!                              │
//! ═══════════════════════════════════════════════════════════════════
//!                              │
//! ┌─────────────────────────────────────────────────────────────────┐
//! │                       KERNEL SPACE                               │
//! │       ┌────────────────────────────────────────────┐            │
//! │       │           Referee Kernel (minimal)         │            │
//! │       │  - Process isolation                       │            │
//! │       │  - Memory protection                       │            │
//! │       │  - Raw NIC driver pass-through             │            │
//! │       └────────────────────────────────────────────┘            │
//! └─────────────────────────────────────────────────────────────────┘
//! ```
//!
//! ## Security Benefits
//!
//! - **Isolation**: Network stack bugs cannot crash the kernel
//! - **Privilege Separation**: No kernel privileges for TCP/IP code
//! - **Auditability**: Network traffic passes through IPC (can be logged)
//! - **Restartability**: Stack can be restarted without system reboot

use std::collections::HashMap;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::time::Instant;

use ea_symbiote::{BlobType, SovereignDocument};
use serde::{Deserialize, Serialize};
use smoltcp::iface::{Config, Interface, SocketSet};
use smoltcp::phy::{Device, DeviceCapabilities, Medium, RxToken, TxToken};
use smoltcp::socket::tcp::{Socket as TcpSocket, SocketBuffer};
use smoltcp::socket::udp::{PacketBuffer, PacketMetadata, Socket as UdpSocket};
use smoltcp::time::Instant as SmolInstant;
use smoltcp::wire::{EthernetAddress, HardwareAddress, IpAddress, IpCidr, Ipv4Address};

// ============================================================================
// IPC Protocol: Network Operation Types
// ============================================================================

/// Network operation request types sent via Symbiote IPC.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NetOperation {
    /// Bind a socket to a local address
    Bind(NetBind),
    /// Listen for incoming connections (TCP)
    Listen(NetListen),
    /// Accept an incoming connection (TCP)
    Accept(NetAccept),
    /// Connect to a remote address (TCP)
    Connect(NetConnect),
    /// Send data on a socket
    Send(NetSend),
    /// Receive data from a socket
    Recv(NetRecv),
    /// Close a socket
    Close(NetClose),
    /// Configure network interface
    Configure(NetConfigure),
    /// Query socket status
    Status(NetStatus),
}

/// Response from network operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NetResponse {
    /// Operation succeeded
    Ok(NetResult),
    /// Operation failed
    Error(NetError),
    /// Data received
    Data(Vec<u8>),
    /// Socket status
    Status(SocketStatus),
}

/// Bind request: associate a socket with a local address
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetBind {
    /// Socket handle (assigned by caller)
    pub socket_id: u64,
    /// Protocol (TCP or UDP)
    pub protocol: Protocol,
    /// Local address to bind to
    pub local_addr: SocketAddrCompact,
}

/// Listen request: start accepting connections
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetListen {
    pub socket_id: u64,
    pub backlog: u32,
}

/// Accept request: accept a pending connection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetAccept {
    pub socket_id: u64,
    /// New socket ID for the accepted connection
    pub new_socket_id: u64,
}

/// Connect request: initiate outbound connection
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetConnect {
    pub socket_id: u64,
    pub protocol: Protocol,
    pub remote_addr: SocketAddrCompact,
}

/// Send request: transmit data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetSend {
    pub socket_id: u64,
    pub data: Vec<u8>,
    /// For UDP: destination address (ignored for TCP)
    pub dest_addr: Option<SocketAddrCompact>,
}

/// Receive request: request data from socket
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetRecv {
    pub socket_id: u64,
    pub max_bytes: usize,
}

/// Close request: terminate socket
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetClose {
    pub socket_id: u64,
}

/// Configure request: set interface parameters
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetConfigure {
    /// IP address with prefix length
    pub ip_cidr: String,
    /// Default gateway
    pub gateway: Option<String>,
    /// MAC address (if changing)
    pub mac_address: Option<[u8; 6]>,
}

/// Status request: query socket state
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetStatus {
    pub socket_id: u64,
}

/// Compact socket address for serialization
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SocketAddrCompact {
    pub ip: [u8; 4], // IPv4 for now
    pub port: u16,
}

impl SocketAddrCompact {
    pub fn new(addr: SocketAddr) -> Self {
        match addr.ip() {
            IpAddr::V4(v4) => Self {
                ip: v4.octets(),
                port: addr.port(),
            },
            IpAddr::V6(_) => panic!("IPv6 not yet supported"),
        }
    }

    pub fn to_socket_addr(&self) -> SocketAddr {
        SocketAddr::new(
            IpAddr::V4(Ipv4Addr::new(self.ip[0], self.ip[1], self.ip[2], self.ip[3])),
            self.port,
        )
    }

    pub fn to_smoltcp(&self) -> (IpAddress, u16) {
        (
            IpAddress::Ipv4(Ipv4Address::new(self.ip[0], self.ip[1], self.ip[2], self.ip[3])),
            self.port,
        )
    }
}

/// Network protocol
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Protocol {
    Tcp,
    Udp,
}

/// Operation result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NetResult {
    pub socket_id: u64,
    pub bytes_transferred: Option<usize>,
}

/// Network error types
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum NetError {
    SocketNotFound,
    AddressInUse,
    ConnectionRefused,
    ConnectionReset,
    ConnectionTimeout,
    NotConnected,
    WouldBlock,
    InvalidAddress,
    InvalidState,
    BufferFull,
    InterfaceDown,
    InternalError(String),
}

/// Socket status information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SocketStatus {
    pub socket_id: u64,
    pub protocol: Protocol,
    pub state: String,
    pub local_addr: Option<SocketAddrCompact>,
    pub remote_addr: Option<SocketAddrCompact>,
    pub bytes_queued: usize,
}

// ============================================================================
// SovereignBlob Implementation for Network IPC
// ============================================================================

/// Network IPC blob for Symbiote transport
#[derive(Debug, Clone)]
pub struct NetBlob {
    pub operation: NetOperation,
    pub request_id: u64,
    pub timestamp: u64,
}

impl SovereignDocument for NetBlob {
    fn blob_type(&self) -> BlobType {
        BlobType::Raw // Network operations are signals
    }

    fn to_bytes(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        // Magic: "NET1"
        buf.extend_from_slice(b"NET1");
        buf.extend_from_slice(&self.request_id.to_le_bytes());
        buf.extend_from_slice(&self.timestamp.to_le_bytes());
        // Serialize operation as JSON (could use more efficient format)
        let op_json = serde_json::to_vec(&self.operation).unwrap_or_default();
        buf.extend_from_slice(&(op_json.len() as u32).to_le_bytes());
        buf.extend_from_slice(&op_json);
        buf
    }

    fn from_bytes(data: &[u8]) -> Option<Self> {
        if data.len() < 24 || &data[0..4] != b"NET1" {
            return None;
        }
        let request_id = u64::from_le_bytes(data[4..12].try_into().ok()?);
        let timestamp = u64::from_le_bytes(data[12..20].try_into().ok()?);
        let op_len = u32::from_le_bytes(data[20..24].try_into().ok()?) as usize;
        if data.len() < 24 + op_len {
            return None;
        }
        let operation: NetOperation = serde_json::from_slice(&data[24..24 + op_len]).ok()?;
        Some(Self {
            operation,
            request_id,
            timestamp,
        })
    }
}

/// Network response blob
#[derive(Debug, Clone)]
pub struct NetResponseBlob {
    pub response: NetResponse,
    pub request_id: u64,
    pub timestamp: u64,
}

impl SovereignDocument for NetResponseBlob {
    fn blob_type(&self) -> BlobType {
        BlobType::Raw
    }

    fn to_bytes(&self) -> Vec<u8> {
        let mut buf = Vec::new();
        // Magic: "NTR1" (Network Response)
        buf.extend_from_slice(b"NTR1");
        buf.extend_from_slice(&self.request_id.to_le_bytes());
        buf.extend_from_slice(&self.timestamp.to_le_bytes());
        let resp_json = serde_json::to_vec(&self.response).unwrap_or_default();
        buf.extend_from_slice(&(resp_json.len() as u32).to_le_bytes());
        buf.extend_from_slice(&resp_json);
        buf
    }

    fn from_bytes(data: &[u8]) -> Option<Self> {
        if data.len() < 24 || &data[0..4] != b"NTR1" {
            return None;
        }
        let request_id = u64::from_le_bytes(data[4..12].try_into().ok()?);
        let timestamp = u64::from_le_bytes(data[12..20].try_into().ok()?);
        let resp_len = u32::from_le_bytes(data[20..24].try_into().ok()?) as usize;
        if data.len() < 24 + resp_len {
            return None;
        }
        let response: NetResponse = serde_json::from_slice(&data[24..24 + resp_len]).ok()?;
        Some(Self {
            response,
            request_id,
            timestamp,
        })
    }
}

// ============================================================================
// Virtual Network Device (for smoltcp)
// ============================================================================

/// A simple loopback/virtual device for testing
pub struct VirtualDevice {
    rx_buffer: Vec<Vec<u8>>,
    tx_buffer: Vec<Vec<u8>>,
    mtu: usize,
}

impl VirtualDevice {
    pub fn new(mtu: usize) -> Self {
        Self {
            rx_buffer: Vec::new(),
            tx_buffer: Vec::new(),
            mtu,
        }
    }

    /// Inject a packet for reception
    pub fn inject_rx(&mut self, packet: Vec<u8>) {
        self.rx_buffer.push(packet);
    }

    /// Extract transmitted packets
    pub fn drain_tx(&mut self) -> Vec<Vec<u8>> {
        std::mem::take(&mut self.tx_buffer)
    }
}

pub struct VirtualRxToken(Vec<u8>);

impl RxToken for VirtualRxToken {
    fn consume<R, F>(self, f: F) -> R
    where
        F: FnOnce(&[u8]) -> R,
    {
        f(&self.0)
    }
}

pub struct VirtualTxToken<'a>(&'a mut Vec<Vec<u8>>);

impl<'a> TxToken for VirtualTxToken<'a> {
    fn consume<R, F>(self, len: usize, f: F) -> R
    where
        F: FnOnce(&mut [u8]) -> R,
    {
        let mut buffer = vec![0u8; len];
        let result = f(&mut buffer);
        self.0.push(buffer);
        result
    }
}

impl Device for VirtualDevice {
    type RxToken<'a> = VirtualRxToken where Self: 'a;
    type TxToken<'a> = VirtualTxToken<'a> where Self: 'a;

    fn receive(&mut self, _timestamp: SmolInstant) -> Option<(Self::RxToken<'_>, Self::TxToken<'_>)> {
        if self.rx_buffer.is_empty() {
            None
        } else {
            let packet = self.rx_buffer.remove(0);
            Some((VirtualRxToken(packet), VirtualTxToken(&mut self.tx_buffer)))
        }
    }

    fn transmit(&mut self, _timestamp: SmolInstant) -> Option<Self::TxToken<'_>> {
        Some(VirtualTxToken(&mut self.tx_buffer))
    }

    fn capabilities(&self) -> DeviceCapabilities {
        let mut caps = DeviceCapabilities::default();
        caps.medium = Medium::Ethernet;
        caps.max_transmission_unit = self.mtu;
        caps
    }
}

// ============================================================================
// Network Manager
// ============================================================================

/// Socket handle tracking
struct SocketHandle {
    smoltcp_handle: smoltcp::iface::SocketHandle,
    protocol: Protocol,
    local_addr: Option<SocketAddrCompact>,
    remote_addr: Option<SocketAddrCompact>,
}

/// The main network stack manager
pub struct NetStackManager<D: Device> {
    /// smoltcp network interface
    interface: Interface,
    /// Socket storage
    sockets: SocketSet<'static>,
    /// The underlying device
    device: D,
    /// Socket handle mapping (our IDs -> smoltcp handles)
    socket_map: HashMap<u64, SocketHandle>,
    /// Next socket ID to assign
    next_socket_id: u64,
    /// Start time for timestamp calculations
    start_time: Instant,
}

impl<D: Device> NetStackManager<D> {
    /// Create a new network stack manager
    pub fn new(mut device: D, mac_address: [u8; 6], ip_cidr: IpCidr) -> Self {
        let config = Config::new(HardwareAddress::Ethernet(EthernetAddress(mac_address)));

        let mut interface = Interface::new(config, &mut device, SmolInstant::from_millis(0));

        interface.update_ip_addrs(|addrs| {
            addrs.push(ip_cidr).ok();
        });

        Self {
            interface,
            sockets: SocketSet::new(vec![]),
            device,
            socket_map: HashMap::new(),
            next_socket_id: 1,
            start_time: Instant::now(),
        }
    }

    /// Get current timestamp for smoltcp
    fn now(&self) -> SmolInstant {
        SmolInstant::from_millis(self.start_time.elapsed().as_millis() as i64)
    }

    /// Poll the network interface
    /// Returns true if there was socket state change
    pub fn poll(&mut self) -> bool {
        use smoltcp::iface::PollResult;
        matches!(
            self.interface.poll(self.now(), &mut self.device, &mut self.sockets),
            PollResult::SocketStateChanged
        )
    }

    /// Handle a network operation request
    pub fn handle_operation(&mut self, op: &NetOperation) -> NetResponse {
        match op {
            NetOperation::Bind(bind) => self.handle_bind(bind),
            NetOperation::Listen(listen) => self.handle_listen(listen),
            NetOperation::Accept(accept) => self.handle_accept(accept),
            NetOperation::Connect(connect) => self.handle_connect(connect),
            NetOperation::Send(send) => self.handle_send(send),
            NetOperation::Recv(recv) => self.handle_recv(recv),
            NetOperation::Close(close) => self.handle_close(close),
            NetOperation::Configure(config) => self.handle_configure(config),
            NetOperation::Status(status) => self.handle_status(status),
        }
    }

    fn handle_bind(&mut self, bind: &NetBind) -> NetResponse {
        let socket_id = bind.socket_id;

        match bind.protocol {
            Protocol::Tcp => {
                let rx_buffer = SocketBuffer::new(vec![0; 65535]);
                let tx_buffer = SocketBuffer::new(vec![0; 65535]);
                let socket = TcpSocket::new(rx_buffer, tx_buffer);
                let handle = self.sockets.add(socket);

                self.socket_map.insert(
                    socket_id,
                    SocketHandle {
                        smoltcp_handle: handle,
                        protocol: Protocol::Tcp,
                        local_addr: Some(bind.local_addr.clone()),
                        remote_addr: None,
                    },
                );

                NetResponse::Ok(NetResult {
                    socket_id,
                    bytes_transferred: None,
                })
            }
            Protocol::Udp => {
                let rx_buffer = PacketBuffer::new(
                    vec![PacketMetadata::EMPTY; 16],
                    vec![0; 65535],
                );
                let tx_buffer = PacketBuffer::new(
                    vec![PacketMetadata::EMPTY; 16],
                    vec![0; 65535],
                );
                let mut socket = UdpSocket::new(rx_buffer, tx_buffer);

                let (ip, port) = bind.local_addr.to_smoltcp();
                if let Err(_) = socket.bind((ip, port)) {
                    return NetResponse::Error(NetError::AddressInUse);
                }

                let handle = self.sockets.add(socket);

                self.socket_map.insert(
                    socket_id,
                    SocketHandle {
                        smoltcp_handle: handle,
                        protocol: Protocol::Udp,
                        local_addr: Some(bind.local_addr.clone()),
                        remote_addr: None,
                    },
                );

                NetResponse::Ok(NetResult {
                    socket_id,
                    bytes_transferred: None,
                })
            }
        }
    }

    fn handle_listen(&mut self, listen: &NetListen) -> NetResponse {
        let Some(socket_handle) = self.socket_map.get(&listen.socket_id) else {
            return NetResponse::Error(NetError::SocketNotFound);
        };

        if socket_handle.protocol != Protocol::Tcp {
            return NetResponse::Error(NetError::InvalidState);
        }

        let local_addr = socket_handle.local_addr.clone();
        let smol_handle = socket_handle.smoltcp_handle;

        let socket = self.sockets.get_mut::<TcpSocket>(smol_handle);
        let (ip, port) = local_addr.as_ref().map(|a| a.to_smoltcp()).unwrap_or((
            IpAddress::Ipv4(Ipv4Address::UNSPECIFIED),
            0,
        ));

        if let Err(_) = socket.listen((ip, port)) {
            return NetResponse::Error(NetError::InvalidState);
        }

        NetResponse::Ok(NetResult {
            socket_id: listen.socket_id,
            bytes_transferred: None,
        })
    }

    fn handle_accept(&mut self, _accept: &NetAccept) -> NetResponse {
        // Accept is handled implicitly by smoltcp - check socket state
        NetResponse::Error(NetError::InternalError(
            "Accept not yet implemented - use poll-based model".into(),
        ))
    }

    fn handle_connect(&mut self, connect: &NetConnect) -> NetResponse {
        if connect.protocol != Protocol::Tcp {
            return NetResponse::Error(NetError::InvalidState);
        }

        let socket_id = connect.socket_id;

        // Create new socket for connection
        let rx_buffer = SocketBuffer::new(vec![0; 65535]);
        let tx_buffer = SocketBuffer::new(vec![0; 65535]);
        let socket = TcpSocket::new(rx_buffer, tx_buffer);
        let handle = self.sockets.add(socket);

        let socket = self.sockets.get_mut::<TcpSocket>(handle);
        let (remote_ip, remote_port) = connect.remote_addr.to_smoltcp();

        // Use ephemeral local port
        let local_port = 49152 + (socket_id as u16 % 16384);

        if let Err(_) = socket.connect(
            self.interface.context(),
            (remote_ip, remote_port),
            local_port,
        ) {
            return NetResponse::Error(NetError::ConnectionRefused);
        }

        self.socket_map.insert(
            socket_id,
            SocketHandle {
                smoltcp_handle: handle,
                protocol: Protocol::Tcp,
                local_addr: None,
                remote_addr: Some(connect.remote_addr.clone()),
            },
        );

        NetResponse::Ok(NetResult {
            socket_id,
            bytes_transferred: None,
        })
    }

    fn handle_send(&mut self, send: &NetSend) -> NetResponse {
        let Some(socket_handle) = self.socket_map.get(&send.socket_id) else {
            return NetResponse::Error(NetError::SocketNotFound);
        };

        match socket_handle.protocol {
            Protocol::Tcp => {
                let socket = self.sockets.get_mut::<TcpSocket>(socket_handle.smoltcp_handle);
                if !socket.may_send() {
                    return NetResponse::Error(NetError::NotConnected);
                }
                match socket.send_slice(&send.data) {
                    Ok(bytes) => NetResponse::Ok(NetResult {
                        socket_id: send.socket_id,
                        bytes_transferred: Some(bytes),
                    }),
                    Err(_) => NetResponse::Error(NetError::BufferFull),
                }
            }
            Protocol::Udp => {
                let socket = self.sockets.get_mut::<UdpSocket>(socket_handle.smoltcp_handle);
                let dest = send.dest_addr.as_ref().ok_or(NetError::InvalidAddress);
                match dest {
                    Ok(addr) => {
                        let (ip, port) = addr.to_smoltcp();
                        match socket.send_slice(&send.data, (ip, port)) {
                            Ok(()) => NetResponse::Ok(NetResult {
                                socket_id: send.socket_id,
                                bytes_transferred: Some(send.data.len()),
                            }),
                            Err(_) => NetResponse::Error(NetError::BufferFull),
                        }
                    }
                    Err(e) => NetResponse::Error(e),
                }
            }
        }
    }

    fn handle_recv(&mut self, recv: &NetRecv) -> NetResponse {
        let Some(socket_handle) = self.socket_map.get(&recv.socket_id) else {
            return NetResponse::Error(NetError::SocketNotFound);
        };

        match socket_handle.protocol {
            Protocol::Tcp => {
                let socket = self.sockets.get_mut::<TcpSocket>(socket_handle.smoltcp_handle);
                if !socket.may_recv() {
                    return NetResponse::Error(NetError::NotConnected);
                }
                let mut buffer = vec![0u8; recv.max_bytes];
                match socket.recv_slice(&mut buffer) {
                    Ok(bytes) => {
                        buffer.truncate(bytes);
                        NetResponse::Data(buffer)
                    }
                    Err(_) => NetResponse::Error(NetError::WouldBlock),
                }
            }
            Protocol::Udp => {
                let socket = self.sockets.get_mut::<UdpSocket>(socket_handle.smoltcp_handle);
                let mut buffer = vec![0u8; recv.max_bytes];
                match socket.recv_slice(&mut buffer) {
                    Ok((bytes, _endpoint)) => {
                        buffer.truncate(bytes);
                        NetResponse::Data(buffer)
                    }
                    Err(_) => NetResponse::Error(NetError::WouldBlock),
                }
            }
        }
    }

    fn handle_close(&mut self, close: &NetClose) -> NetResponse {
        let Some(socket_handle) = self.socket_map.remove(&close.socket_id) else {
            return NetResponse::Error(NetError::SocketNotFound);
        };

        match socket_handle.protocol {
            Protocol::Tcp => {
                let socket = self.sockets.get_mut::<TcpSocket>(socket_handle.smoltcp_handle);
                socket.close();
            }
            Protocol::Udp => {
                let socket = self.sockets.get_mut::<UdpSocket>(socket_handle.smoltcp_handle);
                socket.close();
            }
        }

        // Remove from socket set
        self.sockets.remove(socket_handle.smoltcp_handle);

        NetResponse::Ok(NetResult {
            socket_id: close.socket_id,
            bytes_transferred: None,
        })
    }

    fn handle_configure(&mut self, config: &NetConfigure) -> NetResponse {
        // Parse and apply IP configuration
        if let Ok(cidr) = config.ip_cidr.parse::<IpCidr>() {
            self.interface.update_ip_addrs(|addrs| {
                addrs.clear();
                addrs.push(cidr).ok();
            });
        }

        // Configure gateway if provided
        if let Some(ref gw_str) = config.gateway {
            if let Ok(gw) = gw_str.parse::<Ipv4Addr>() {
                self.interface.routes_mut().add_default_ipv4_route(
                    Ipv4Address::new(gw.octets()[0], gw.octets()[1], gw.octets()[2], gw.octets()[3]),
                ).ok();
            }
        }

        NetResponse::Ok(NetResult {
            socket_id: 0,
            bytes_transferred: None,
        })
    }

    fn handle_status(&mut self, status: &NetStatus) -> NetResponse {
        let Some(socket_handle) = self.socket_map.get(&status.socket_id) else {
            return NetResponse::Error(NetError::SocketNotFound);
        };

        let state_str = match socket_handle.protocol {
            Protocol::Tcp => {
                let socket = self.sockets.get::<TcpSocket>(socket_handle.smoltcp_handle);
                format!("{:?}", socket.state())
            }
            Protocol::Udp => "Bound".to_string(),
        };

        NetResponse::Status(SocketStatus {
            socket_id: status.socket_id,
            protocol: socket_handle.protocol,
            state: state_str,
            local_addr: socket_handle.local_addr.clone(),
            remote_addr: socket_handle.remote_addr.clone(),
            bytes_queued: 0, // Would need to query socket buffers
        })
    }
}

// ============================================================================
// Tests
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_socket_addr_compact_roundtrip() {
        let addr = SocketAddr::new(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 1)), 8080);
        let compact = SocketAddrCompact::new(addr);
        let recovered = compact.to_socket_addr();
        assert_eq!(addr, recovered);
    }

    #[test]
    fn test_net_blob_serialization() {
        let blob = NetBlob {
            operation: NetOperation::Bind(NetBind {
                socket_id: 1,
                protocol: Protocol::Tcp,
                local_addr: SocketAddrCompact {
                    ip: [0, 0, 0, 0],
                    port: 8080,
                },
            }),
            request_id: 42,
            timestamp: 12345,
        };

        let bytes = blob.to_bytes();
        let recovered = NetBlob::from_bytes(&bytes).expect("deserialize");

        assert_eq!(recovered.request_id, 42);
        assert_eq!(recovered.timestamp, 12345);
    }

    #[test]
    fn test_virtual_device() {
        let mut device = VirtualDevice::new(1500);
        device.inject_rx(vec![1, 2, 3, 4]);

        let caps = device.capabilities();
        assert_eq!(caps.max_transmission_unit, 1500);
        assert_eq!(caps.medium, Medium::Ethernet);
    }

    #[test]
    fn test_protocol_serialization() {
        let tcp = Protocol::Tcp;
        let udp = Protocol::Udp;

        let tcp_json = serde_json::to_string(&tcp).unwrap();
        let udp_json = serde_json::to_string(&udp).unwrap();

        assert_eq!(tcp_json, "\"Tcp\"");
        assert_eq!(udp_json, "\"Udp\"");
    }
}
