use crate::world::Chunk;
use crate::world::block::{Block, BlockType};
use crate::world::chunk::{CHUNK_WIDTH, CHUNK_DEPTH};

pub fn generate_flat_terrain(chunk: &mut Chunk, height: u32) {
    for x in 0..CHUNK_WIDTH {
        for z in 0..CHUNK_DEPTH {
            for y in 0..256 {
                let btype = if y < height - 1 {
                    BlockType::Stone
                } else if y < height {
                    BlockType::Dirt
                } else if y == height {
                    BlockType::Grass
                } else {
                    continue;
                };
                chunk.set_block(x as usize, y as usize, z as usize, Block { btype });
            }
        }
    }
}

pub fn generate_varied_terrain(chunk: &mut Chunk, chunk_x: i32, chunk_z: i32) {
    for x in 0..CHUNK_WIDTH {
        for z in 0..CHUNK_DEPTH {
            let world_x = (chunk_x * CHUNK_WIDTH as i32 + x as i32) as f32;
            let world_z = (chunk_z * CHUNK_DEPTH as i32 + z as i32) as f32;
            
            let h = ( (world_x * 0.1).sin() * 4.0 + (world_z * 0.1).cos() * 4.0 + 64.0 ) as u32;
            
            for y in 0..256 {
                let btype = if y < h - 2 {
                    BlockType::Stone
                } else if y < h {
                    BlockType::Dirt
                } else if y == h {
                    BlockType::Grass
                } else {
                    continue;
                };
                chunk.set_block(x as usize, y as usize, z as usize, Block { btype });
            }
        }
    }
}

