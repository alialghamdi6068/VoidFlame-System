use std::sync::Arc;
use tokio::sync::RwLock;
#[derive(Clone)]
pub struct State { pub maintenance: Arc<RwLock<bool>> }
impl State { pub fn new() -> Self { Self { maintenance: Arc::new(RwLock::new(false)) } } }
