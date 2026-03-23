use std::fs::{self, File};
use std::io::{Read, Write};
use std::path::PathBuf;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use crate::world::Chunk;

pub fn get_chunk_path(world_dir: &str, x: i32, z: i32) -> PathBuf {
    let mut path = PathBuf::from(world_dir);
    path.push("chunks");
    path.push(format!("c_{}_{}.bin", x, z));
    path
}

pub fn save_chunk(world_dir: &str, x: i32, z: i32, chunk: &Chunk) -> anyhow::Result<()> {
    let path = get_chunk_path(world_dir, x, z);
    
    // Ensure directory exists
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }

    let encoded: Vec<u8> = bincode::serialize(chunk)?;
    
    let file = File::create(path)?;
    let mut encoder = GzEncoder::new(file, Compression::default());
    encoder.write_all(&encoded)?;
    encoder.finish()?;
    
    Ok(())
}

pub fn load_chunk(world_dir: &str, x: i32, z: i32) -> anyhow::Result<Option<Chunk>> {
    let path = get_chunk_path(world_dir, x, z);
    
    if !path.exists() {
        return Ok(None);
    }

    let file = File::open(path)?;
    let mut decoder = GzDecoder::new(file);
    let mut decoded = Vec::new();
    decoder.read_to_end(&mut decoded)?;
    
    let chunk: Chunk = bincode::deserialize(&decoded)?;
    Ok(Some(chunk))
}
