use glam::Vec3;

pub trait Entity {
    fn update(&mut self, dt: std::time::Duration, world: &crate::world::World);
    fn position(&self) -> Vec3;
}

pub mod player;
