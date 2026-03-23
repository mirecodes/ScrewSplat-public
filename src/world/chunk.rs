use super::block::{Block, BlockType};

pub const CHUNK_WIDTH: usize = 16;
pub const CHUNK_HEIGHT: usize = 256;
pub const CHUNK_DEPTH: usize = 16;
pub const CHUNK_VOLUME: usize = CHUNK_WIDTH * CHUNK_HEIGHT * CHUNK_DEPTH;

pub struct Chunk {
    pub blocks: Box<[Block; CHUNK_VOLUME]>,
}

impl Default for Chunk {
    fn default() -> Self {
        Self {
            blocks: Box::new([Block::new(BlockType::Air); CHUNK_VOLUME]),
        }
    }
}

impl Chunk {
    pub fn new() -> Self {
        Self::default()
    }

    #[inline]
    pub fn get_block(&self, x: usize, y: usize, z: usize) -> Option<Block> {
        if x >= CHUNK_WIDTH || y >= CHUNK_HEIGHT || z >= CHUNK_DEPTH {
            return None;
        }
        Some(self.blocks[x + y * CHUNK_WIDTH * CHUNK_DEPTH + z * CHUNK_WIDTH])
    }

    #[inline]
    pub fn set_block(&mut self, x: usize, y: usize, z: usize, block: Block) {
        if x < CHUNK_WIDTH && y < CHUNK_HEIGHT && z < CHUNK_DEPTH {
            self.blocks[x + y * CHUNK_WIDTH * CHUNK_DEPTH + z * CHUNK_WIDTH] = block;
        }
    }
    
    pub fn generate_flat(&mut self) {
        for x in 0..CHUNK_WIDTH {
            for z in 0..CHUNK_DEPTH {
                for y in 0..CHUNK_HEIGHT {
                    let block_type = if y == 64 {
                        BlockType::Grass
                    } else if y < 64 && y > 60 {
                        BlockType::Dirt
                    } else if y <= 60 {
                        BlockType::Stone
                    } else {
                        BlockType::Air
                    };
                    self.set_block(x, y, z, Block::new(block_type));
                }
            }
        }
    }
}
