use bytemuck::{Pod, Zeroable};

#[repr(C)]
#[derive(Debug, Copy, Clone, Pod, Zeroable)]
pub struct LightUniform {
    pub direction: [f32; 3],
    pub _padding: u32,
    pub color: [f32; 3],
    pub ambient_intensity: f32,
}

impl LightUniform {
    pub fn new(direction: [f32; 3], color: [f32; 3], ambient: f32) -> Self {
        Self {
            direction,
            _padding: 0,
            color,
            ambient_intensity: ambient,
        }
    }
}
