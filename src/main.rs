mod app;
mod camera;
mod controller;
mod entity;
mod render;
mod mesh;
mod world;

fn main() {
    env_logger::init();
    app::run();
}
