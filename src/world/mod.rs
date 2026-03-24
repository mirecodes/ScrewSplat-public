use std::collections::HashMap;
use crate::entity::Entity;
pub mod block;
pub mod chunk;
pub mod terrain;
pub mod storage;

pub use chunk::Chunk;
pub use block::BlockType;
use glam::Vec3;
use std::sync::mpsc::{self, Sender, Receiver};
use std::collections::HashSet;
use std::thread;

pub struct World {
    pub chunks: HashMap<(i32, i32), Chunk>,
    pub entities: Vec<Box<dyn Entity>>,
    pub render_distance: i32,
    pub loading_chunks: HashSet<(i32, i32)>,
    pub chunk_receiver: Receiver<(i32, i32, Chunk)>,
    pub chunk_sender: Sender<(i32, i32, Chunk)>,
}

impl World {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::channel();
        Self {
            chunks: HashMap::new(),
            entities: Vec::new(),
            render_distance: 8,
            loading_chunks: HashSet::new(),
            chunk_receiver: rx,
            chunk_sender: tx,
        }
    }

    pub fn request_chunk_load(&mut self, x: i32, z: i32) {
        if self.loading_chunks.contains(&(x, z)) || self.chunks.contains_key(&(x, z)) {
            return;
        }

        self.loading_chunks.insert((x, z));
        let tx = self.chunk_sender.clone();
        
        thread::spawn(move || {
            // First try loading from disk
            let world_dir = "worlds/test_world"; // Hardcoded for now
            match storage::load_chunk(world_dir, x, z) {
                Ok(Some(chunk)) => {
                    let _ = tx.send((x, z, chunk));
                }
                Ok(None) | Err(_) => {
                    // Generate new chunk if not found or error
                    let mut chunk = Chunk::new();
                    terrain::generate_varied_terrain(&mut chunk, x, z);
                    let _ = tx.send((x, z, chunk));
                }
            }
        });
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

    pub fn update_chunks_around_player(&mut self, player_pos: Vec3) -> Vec<(i32, i32)> {
        let px = (player_pos.x / 16.0).floor() as i32;
        let pz = (player_pos.z / 16.0).floor() as i32;

        let r = self.render_distance;
        for x in (px - r)..=(px + r) {
            for z in (pz - r)..=(pz + r) {
                let dx = x - px;
                let dz = z - pz;
                if dx * dx + dz * dz <= r * r {
                    if !self.chunks.contains_key(&(x, z)) && !self.loading_chunks.contains(&(x, z)) {
                        self.request_chunk_load(x, z);
                    }
                }
            }
        }

        // Unload far chunks
        let mut to_remove = Vec::new();
        let unload_r = r + 2;
        for &pos in self.chunks.keys() {
            let dx = pos.0 - px;
            let dz = pos.1 - pz;
            if dx * dx + dz * dz > unload_r * unload_r {
                to_remove.push(pos);
            }
        }

        for pos in &to_remove {
            if let Some(chunk) = self.chunks.remove(pos) {
                let _ = storage::save_chunk("worlds/test_world", pos.0, pos.1, &chunk);
            }
        }
        
        to_remove
    }

    pub fn is_area_loaded(&self, center_x: f32, center_z: f32, radius: i32) -> bool {
        let px = (center_x / 16.0).floor() as i32;
        let pz = (center_z / 16.0).floor() as i32;

        for x in (px - radius)..=(px + radius) {
            for z in (pz - radius)..=(pz + radius) {
                let dx = x - px;
                let dz = z - pz;
                if dx * dx + dz * dz <= radius * radius {
                    if !self.chunks.contains_key(&(x, z)) {
                        return false;
                    }
                }
            }
        }
        true
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

    pub fn get_highest_block_y(&self, x: f32, z: f32) -> f32 {
        let ix = x.floor() as i32;
        let iz = z.floor() as i32;
        for y in (0..256).rev() {
            if !self.get_block_global(ix, y, iz).is_transparent() {
                return (y + 1) as f32;
            }
        }
        80.0 // Fallback
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
