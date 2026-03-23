use std::collections::HashMap;
use crate::entity::Entity;
pub mod block;
pub mod chunk;
pub mod terrain;

pub use chunk::Chunk;
pub use block::BlockType;
use glam::Vec3;

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

    pub fn update(&mut self, _dt: std::time::Duration) {
        // Entity updates are currently handled in App to avoid borrow checker issues 
        // with passing &World to entities owned by World.
    }

    pub fn add_chunk(&mut self, x: i32, z: i32, chunk: Chunk) {
        self.chunks.insert((x, z), chunk);
    }

    pub fn get_chunk(&self, x: i32, z: i32) -> Option<&Chunk> {
        self.chunks.get(&(x, z))
    }

    pub fn get_block_global(&self, x: i32, y: i32, z: i32) -> BlockType {
        if y < 0 || y >= 256 {
            return BlockType::Air;
        }

        let cx = x.div_euclid(16);
        let cz = z.div_euclid(16);
        let lx = x.rem_euclid(16) as usize;
        let lz = z.rem_euclid(16) as usize;

        if let Some(chunk) = self.get_chunk(cx, cz) {
            if let Some(block) = chunk.get_block(lx, y as usize, lz) {
                return block.btype;
            }
        }

        BlockType::Air
    }

    pub fn has_solid_block_in_aabb(&self, min: Vec3, max: Vec3) -> bool {
        let x_min = min.x.floor() as i32;
        let x_max = max.x.ceil() as i32;
        let y_min = min.y.floor() as i32;
        let y_max = max.y.ceil() as i32;
        let z_min = min.z.floor() as i32;
        let z_max = max.z.ceil() as i32;

        for x in x_min..x_max {
            for y in y_min..y_max {
                for z in z_min..z_max {
                    if !self.get_block_global(x, y, z).is_transparent() {
                        return true;
                    }
                }
            }
        }
        false
    }

    pub fn add_entity(&mut self, entity: Box<dyn Entity>) {
        self.entities.push(entity);
    }
}
