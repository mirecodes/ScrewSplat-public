use glam::Vec3;

pub trait Entity {
    fn update(&mut self, dt: std::time::Duration);
    fn position(&self) -> Vec3;
}

pub mod player;
