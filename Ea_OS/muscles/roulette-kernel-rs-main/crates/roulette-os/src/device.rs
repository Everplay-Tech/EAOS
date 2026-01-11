//! Device driver interface: robust, enterprise-grade

use async_trait::async_trait;

/// Device type abstraction
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeviceType {
    Block,
    Character,
    Network,
    Other,
}

/// Algebraic device event
#[derive(Debug, Clone)]
pub enum DeviceEvent {
    DataRead(Vec<u8>),
    DataWritten(usize),
    Hotplugged(String),
    Error(DeviceError),
}

#[derive(Debug, Clone)]
pub enum DeviceError {
    NotReady,
    IoError,
    NotFound,
    PermissionDenied,
    Other(String),
}

/// Device trait: async, algebraic events
#[async_trait]
pub trait Device {
    async fn init(&mut self) -> Result<DeviceEvent, DeviceError>;
    async fn read(&mut self, len: usize) -> Result<DeviceEvent, DeviceError>;
    async fn write(&mut self, data: &[u8]) -> Result<DeviceEvent, DeviceError>;
    async fn shutdown(&mut self) -> Result<DeviceEvent, DeviceError>;
    fn name(&self) -> &str;
    fn device_type(&self) -> DeviceType;
    fn hotplug(&mut self) -> bool { false }
}

/// Algebraic device operation
#[derive(Debug, Clone)]
pub enum DevOp {
    Init,
    Read(String, usize),
    Write(String, Vec<u8>),
    Shutdown,
    ListByType(DeviceType),
}

/// Algebraic device result
#[derive(Debug, Clone)]
pub enum DevResult {
    Initialized,
    Data(Vec<u8>),
    Written(usize),
    Shutdown,
    DeviceList(Vec<String>),
    Error(DeviceError),
}

/// Device manager: registry, hotplug, abstraction, async, algebraic ops
pub struct DeviceManager<'a> {
    devices: heapless::Vec<&'a mut (dyn Device + Send), 16>,
}

impl<'a> DeviceManager<'a> {
    /// Create a new device manager
    pub const fn new() -> Self {
        Self { devices: heapless::Vec::new() }
    }

    /// Register a device (hotplug support)
    pub fn register(&mut self, device: &'a mut (dyn Device + Send)) -> Result<(), &'static str> {
        if device.hotplug() {
            println!("Hotplugged device: {}", device.name());
        }
        self.devices.push(device).map_err(|_| "Device registry full")
    }

    /// Async algebraic device operation
    pub async fn op(&mut self, op: DevOp) -> DevResult {
        match op {
            DevOp::Init => {
                for dev in self.devices.iter_mut() {
                    let _ = dev.init().await;
                }
                DevResult::Initialized
            }
            DevOp::Read(name, len) => {
                for dev in self.devices.iter_mut() {
                    if dev.name() == name {
                        match dev.read(len).await {
                            Ok(DeviceEvent::DataRead(data)) => return DevResult::Data(data),
                            Ok(DeviceEvent::Error(e)) => return DevResult::Error(e),
                            Err(e) => return DevResult::Error(e),
                            _ => continue,
                        }
                    }
                }
                DevResult::Error(DeviceError::NotFound)
            }
            DevOp::Write(name, data) => {
                for dev in self.devices.iter_mut() {
                    if dev.name() == name {
                        match dev.write(&data).await {
                            Ok(DeviceEvent::DataWritten(sz)) => return DevResult::Written(sz),
                            Ok(DeviceEvent::Error(e)) => return DevResult::Error(e),
                            Err(e) => return DevResult::Error(e),
                            _ => continue,
                        }
                    }
                }
                DevResult::Error(DeviceError::NotFound)
            }
            DevOp::Shutdown => {
                for dev in self.devices.iter_mut() {
                    let _ = dev.shutdown().await;
                }
                DevResult::Shutdown
            }
            DevOp::ListByType(dtype) => {
                let list = self.devices.iter().filter(|d| d.device_type() == dtype).map(|d| d.name().to_string()).collect();
                DevResult::DeviceList(list)
            }
        }
    }
}
