use serde::{Serialize, Deserialize};

#[derive(Copy, Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum BlockType {
    Air,
    Grass,
    Dirt,
    Stone,
}

impl BlockType {
    pub fn is_transparent(&self) -> bool {
        match self {
            BlockType::Air => true,
            _ => false,
        }
    }
}

// Represents a 1x1x1 Voxel
#[derive(Copy, Clone, Debug, Serialize, Deserialize)]
pub struct Block {
    pub btype: BlockType,
}

impl Block {
    pub fn new(btype: BlockType) -> Self {
        Self { btype }
    }
}
