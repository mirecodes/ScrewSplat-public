use std::collections::HashMap;
use crate::entity::Entity;
pub mod block;
pub mod chunk;
pub mod terrain;

pub use chunk::Chunk;
pub use block::BlockType;

pub struct World {
    pub chunks: HashMap<(i32, i32), Chunk>,
    pub entities: Vec<Box<dyn Entity>>,
}

impl World {
    pub fn new() -> Self {
        Self {
            chunks: HashMap::new(),
            entities: Vec::new(),
        }
    }

    pub fn update(&mut self, dt: std::time::Duration) {
        for entity in &mut self.entities {
            entity.update(dt);
        }
    }

    pub fn add_chunk(&mut self, x: i32, z: i32, chunk: Chunk) {
        self.chunks.insert((x, z), chunk);
    }

    pub fn get_chunk(&self, x: i32, z: i32) -> Option<&Chunk> {
        self.chunks.get(&(x, z))
    }

    pub fn add_entity(&mut self, entity: Box<dyn Entity>) {
        self.entities.push(entity);
    }
}
