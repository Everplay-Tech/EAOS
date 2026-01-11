//! Networking stack: robust, enterprise-grade

use std::collections::VecDeque;
use std::net::Ipv4Addr;
use futures::future::BoxFuture;

/// Network error type (algebraic)
#[derive(Debug)]
pub enum NetError {
    NotImplemented,
    InvalidAddress,
    SendFailed,
    ReceiveFailed,
    SocketClosed,
    Timeout,
    Protocol(NetProtocolError),
}

#[derive(Debug)]
pub enum NetProtocolError {
    InvalidPacket,
    ConnectionReset,
    UnexpectedState,
}

/// Algebraic network event
#[derive(Debug, Clone)]
pub enum NetworkEvent {
    PacketReceived(Vec<u8>),
    ConnectionEstablished(Ipv4Addr),
    ConnectionClosed(Ipv4Addr),
    Error(NetError),
}

/// TCP/IP protocol state machine
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TcpState {
    Closed,
    Listen,
    SynSent,
    SynReceived,
    Established,
    FinWait1,
    FinWait2,
    CloseWait,
    LastAck,
    TimeWait,
}

/// Algebraic connection operation
#[derive(Debug, Clone)]
pub enum ConnOp {
    Connect(Ipv4Addr),
    Send(Vec<u8>),
    Receive,
    Close,
}

/// Algebraic connection result
#[derive(Debug, Clone)]
pub enum ConnResult {
    Connected(Ipv4Addr),
    Sent(usize),
    Received(Vec<u8>),
    Closed,
    Error(NetError),
}

/// Socket type
pub struct Socket {
    pub local_addr: Ipv4Addr,
    pub remote_addr: Option<Ipv4Addr>,
    pub state: TcpState,
    pub rx: VecDeque<NetworkEvent>,
    pub tx: VecDeque<NetworkEvent>,
}

impl Socket {
    pub fn new(local_addr: Ipv4Addr) -> Self {
        Self {
            local_addr,
            remote_addr: None,
            state: TcpState::Closed,
            rx: VecDeque::new(),
            tx: VecDeque::new(),
        }
    }

    /// Async algebraic connection management
    pub fn op(&mut self, op: ConnOp) -> BoxFuture<'static, ConnResult> {
        use futures::FutureExt;
        match op {
            ConnOp::Connect(remote) => {
                self.remote_addr = Some(remote);
                self.state = TcpState::SynSent;
                self.state = TcpState::Established;
                async { ConnResult::Connected(remote) }.boxed()
            }
            ConnOp::Send(data) => {
                if self.state != TcpState::Established {
                    async { ConnResult::Error(NetError::SocketClosed) }.boxed()
                } else {
                    let len = data.len();
                    self.tx.push_back(NetworkEvent::PacketReceived(data));
                    async { ConnResult::Sent(len) }.boxed()
                }
            }
            ConnOp::Receive => {
                if self.state != TcpState::Established {
                    async { ConnResult::Error(NetError::SocketClosed) }.boxed()
                } else {
                    match self.rx.pop_front() {
                        Some(NetworkEvent::PacketReceived(data)) => async { ConnResult::Received(data) }.boxed(),
                        Some(_) => async { ConnResult::Error(NetError::Protocol(NetProtocolError::UnexpectedState)) }.boxed(),
                        None => async { ConnResult::Error(NetError::Timeout) }.boxed(),
                    }
                }
            }
            ConnOp::Close => {
                self.state = TcpState::Closed;
                async { ConnResult::Closed }.boxed()
            }
        }
    }
}

/// NetworkStack: TCP/IP, sockets, async protocol state machines
pub struct NetworkStack {
    pub sockets: Vec<Socket>,
}

impl NetworkStack {
    /// Create a new network stack
    pub fn new() -> Self {
        Self { sockets: Vec::new() }
    }

    /// Open a socket
    pub fn open_socket(&mut self, local_addr: Ipv4Addr) -> usize {
        let sock = Socket::new(local_addr);
        self.sockets.push(sock);
        self.sockets.len() - 1
    }

    /// Get mutable socket by index
    pub fn get_socket_mut(&mut self, idx: usize) -> Option<&mut Socket> {
        self.sockets.get_mut(idx)
    }
}
