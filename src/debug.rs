use sysinfo::System;
use std::time::{Duration, Instant};

pub struct SystemMonitor {
    sys: System,
    last_update: Instant,
    update_interval: Duration,
    
    cpu_usage: f32,
    mem_usage: f32,
}

impl SystemMonitor {
    pub fn new() -> Self {
        let mut sys = System::new_all();
        sys.refresh_all();
        
        Self {
            sys,
            last_update: Instant::now(),
            update_interval: Duration::from_millis(1000),
            cpu_usage: 0.0,
            mem_usage: 0.0,
        }
    }

    pub fn update(&mut self) {
        if self.last_update.elapsed() >= self.update_interval {
            self.sys.refresh_cpu_all();
            self.sys.refresh_memory();
            
            self.cpu_usage = self.sys.global_cpu_usage();
            
            let used_mem = self.sys.used_memory() as f32;
            let total_mem = self.sys.total_memory() as f32;
            self.mem_usage = (used_mem / total_mem) * 100.0;
            
            self.last_update = Instant::now();
        }
    }

    pub fn cpu_usage(&self) -> f32 {
        self.cpu_usage
    }

    pub fn mem_usage(&self) -> f32 {
        self.mem_usage
    }
}
