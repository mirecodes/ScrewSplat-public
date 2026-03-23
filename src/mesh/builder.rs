use super::vertex::Vertex;
use crate::world::chunk::{Chunk, CHUNK_WIDTH, CHUNK_HEIGHT, CHUNK_DEPTH};
use crate::world::block::BlockType;

pub struct Mesh {
    pub vertices: Vec<Vertex>,
    pub indices: Vec<u32>,
}

pub fn build_chunk_mesh(chunk: &Chunk, world_offset: glam::Vec3) -> Mesh {
    let mut vertices = Vec::new();
    let mut indices = Vec::new();

    for y in 0..CHUNK_HEIGHT {
        for z in 0..CHUNK_DEPTH {
            for x in 0..CHUNK_WIDTH {
                if let Some(block) = chunk.get_block(x, y, z) {
                    if block.btype == BlockType::Air {
                        continue;
                    }

                    let neighbors = [
                        (x as i32, y as i32 + 1, z as i32, 0),
                        (x as i32, y as i32 - 1, z as i32, 1),
                        (x as i32 + 1, y as i32, z as i32, 2),
                        (x as i32 - 1, y as i32, z as i32, 3),
                        (x as i32, y as i32, z as i32 + 1, 4),
                        (x as i32, y as i32, z as i32 - 1, 5),
                    ];

                    for (nx, ny, nz, face) in neighbors {
                        let is_visible = if nx < 0 || ny < 0 || nz < 0 || 
                            nx >= CHUNK_WIDTH as i32 || 
                            ny >= CHUNK_HEIGHT as i32 || 
                            nz >= CHUNK_DEPTH as i32 {
                            true
                        } else {
                            if let Some(nblock) = chunk.get_block(nx as usize, ny as usize, nz as usize) {
                                nblock.btype.is_transparent()
                            } else {
                                true
                            }
                        };

                        if is_visible {
                            add_face(&mut vertices, &mut indices, x as f32 + world_offset.x, y as f32 + world_offset.y, z as f32 + world_offset.z, face, block.btype);
                        }
                    }
                }
            }
        }
    }

    Mesh { vertices, indices }
}

fn add_face(vertices: &mut Vec<Vertex>, indices: &mut Vec<u32>, x: f32, y: f32, z: f32, face: usize, btype: BlockType) {
    let start_idx = vertices.len() as u32;

    let p = [
        [x, y+1.0, z+1.0], [x+1.0, y+1.0, z+1.0], [x+1.0, y+1.0, z], [x, y+1.0, z],
        [x, y, z], [x+1.0, y, z], [x+1.0, y, z+1.0], [x, y, z+1.0],
        [x+1.0, y, z+1.0], [x+1.0, y, z], [x+1.0, y+1.0, z], [x+1.0, y+1.0, z+1.0],
        [x, y, z], [x, y, z+1.0], [x, y+1.0, z+1.0], [x, y+1.0, z],
        [x, y, z+1.0], [x+1.0, y, z+1.0], [x+1.0, y+1.0, z+1.0], [x, y+1.0, z+1.0],
        [x+1.0, y, z], [x, y, z], [x, y+1.0, z], [x+1.0, y+1.0, z],
    ];

    let n = [
        [0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [1.0, 0.0, 0.0],
        [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, -1.0]
    ];
    let norm = n[face];

    let tx = match btype {
        BlockType::Grass => match face { 0 => 0, 1 => 2, _ => 1 },
        BlockType::Dirt => 2,
        BlockType::Stone => 3,
        _ => 0,
    };
    let u_min_f = tx as f32 * 0.25;
    let u_max_f = u_min_f + 0.25;
    
    // Y atlas coordinate is always 0 in this 4x1 grid
    let v_min = 0.0;
    let v_max = 0.25;

    let uv_map = [
        [u_min_f, v_max], [u_max_f, v_max], [u_max_f, v_min], [u_min_f, v_min],
    ];

    for i in 0..4 {
        vertices.push(Vertex {
            position: p[face * 4 + i],
            tex_coords: uv_map[i],
            normal: norm,
        });
    }

    indices.extend_from_slice(&[
        start_idx, start_idx + 1, start_idx + 2,
        start_idx, start_idx + 2, start_idx + 3,
    ]);
}
