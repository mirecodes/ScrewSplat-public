use winit::{
    application::ApplicationHandler,
    event::*,
    event_loop::{ActiveEventLoop, EventLoop},
    window::{Window, WindowId},
};
use std::sync::Arc;

use crate::render::{context::WgpuContext, pipeline::RenderPipeline, buffer::Buffer, texture::Texture};
use crate::camera::CameraUniform;
use crate::entity::player::Player;
use crate::entity::Entity;
use crate::world::Chunk;
use crate::world::World;
use crate::render::light::LightUniform;
use crate::mesh::builder::build_chunk_mesh;
use crate::world::terrain::generate_varied_terrain;
use winit::window::CursorGrabMode;
use glam::Vec3;
use std::collections::HashMap;

struct ChunkRenderData {
    vertex_buffer: Buffer<crate::mesh::vertex::Vertex>,
    index_buffer: Buffer<u32>,
    num_indices: u32,
}

struct App {
    window: Option<Arc<Window>>,
    render_context: Option<WgpuContext>,
    render_pipeline: Option<RenderPipeline>,
    
    // Rendering resources
    render_chunks: HashMap<(i32, i32), ChunkRenderData>,
    world: Option<World>,
    player: Option<Player>,
    camera_uniform: Option<CameraUniform>,
    camera_buffer: Option<Buffer<CameraUniform>>,
    light_uniform: Option<LightUniform>,
    light_buffer: Option<Buffer<LightUniform>>,
    bind_group: Option<wgpu::BindGroup>,
    
    last_render_time: std::time::Instant,
}

impl Default for App {
    fn default() -> Self {
        Self {
            window: None,
            render_context: None,
            render_pipeline: None,
            render_chunks: HashMap::new(),
            world: None,
            player: None,
            camera_uniform: None,
            camera_buffer: None,
            light_uniform: None,
            light_buffer: None,
            bind_group: None,
            last_render_time: std::time::Instant::now(),
        }
    }
}

impl ApplicationHandler for App {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.window.is_none() {
            let window_attributes = Window::default_attributes()
                .with_title("3D Voxel Engine")
                .with_inner_size(winit::dpi::LogicalSize::new(1280.0, 720.0));
            
            let window = Arc::new(event_loop.create_window(window_attributes).unwrap());
            self.window = Some(window.clone());
            
            let context = pollster::block_on(WgpuContext::new(window.clone()));
            let pipeline = RenderPipeline::new(&context);
            
            // World generation
            let mut world = World::new();
            let mut render_chunks = HashMap::new();
            
            // Generate 3x3 chunks
            for cz in -1..=1 {
                for cx in -1..=1 {
                    let mut chunk = Chunk::new();
                    generate_varied_terrain(&mut chunk, cx, cz);
                    
                    let mesh = build_chunk_mesh(&chunk, cx, cz, |x, y, z| {
                        world.get_block_global(x, y, z)
                    });
                    let v_buf = Buffer::new_vertex(&context.device, &mesh.vertices);
                    let i_buf = Buffer::<u32>::new_index(&context.device, &mesh.indices);
                    
                    render_chunks.insert((cx, cz), ChunkRenderData {
                        vertex_buffer: v_buf,
                        index_buffer: i_buf,
                        num_indices: mesh.indices.len() as u32,
                    });
                    
                    world.add_chunk(cx, cz, chunk);
                }
            }
            
            // Player setup
            let aspect = context.config.width as f32 / context.config.height as f32;
            let player = Player::new((8.0, 80.0, 8.0).into(), -std::f32::consts::FRAC_PI_2, -0.8, aspect);
            let mut camera_uniform = CameraUniform::new();
            camera_uniform.update_view_proj(&player.camera, player.position, player.yaw, player.pitch);
            let camera_buffer = Buffer::new_uniform(&context.device, &[camera_uniform]);
            
            // Light setup
            let light_uniform = LightUniform::new(
                [-0.5, -1.0, -0.3], // Direction
                [1.0, 1.0, 1.0],    // Color
                0.3                 // Ambient
            );
            let light_buffer = Buffer::new_uniform(&context.device, &[light_uniform]);
            
            // Texture setup
            let texture = Texture::generate_atlas(&context.device, &context.queue);
            
            // Bind Group
            let bind_group = context.device.create_bind_group(&wgpu::BindGroupDescriptor {
                layout: &pipeline.bind_group_layout,
                entries: &[
                    wgpu::BindGroupEntry {
                        binding: 0,
                        resource: camera_buffer.buffer.as_entire_binding(),
                    },
                    wgpu::BindGroupEntry {
                        binding: 1,
                        resource: wgpu::BindingResource::TextureView(&texture.view),
                    },
                    wgpu::BindGroupEntry {
                        binding: 2,
                        resource: wgpu::BindingResource::Sampler(&texture.sampler),
                    },
                    wgpu::BindGroupEntry {
                        binding: 3,
                        resource: light_buffer.buffer.as_entire_binding(),
                    },
                ],
                label: Some("Main Bind Group"),
            });
            
            // Grab cursor
            window.set_cursor_grab(CursorGrabMode::Confined)
                .or_else(|_| window.set_cursor_grab(CursorGrabMode::Locked))
                .unwrap_or(());
            window.set_cursor_visible(false);

            self.render_pipeline = Some(pipeline);
            self.render_context = Some(context);
            self.render_chunks = render_chunks;
            self.world = Some(world);
            self.player = Some(player);
            self.camera_uniform = Some(camera_uniform);
            self.camera_buffer = Some(camera_buffer);
            self.light_uniform = Some(light_uniform);
            self.light_buffer = Some(light_buffer);
            self.bind_group = Some(bind_group);
            self.last_render_time = std::time::Instant::now();
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => {
                event_loop.exit();
            }
            WindowEvent::Resized(physical_size) => {
                if let Some(context) = &mut self.render_context {
                    context.resize(physical_size);
                }
            }
            WindowEvent::KeyboardInput { 
                event: KeyEvent {
                    physical_key,
                    state,
                    ..
                },
                ..
            } => {
                if let Some(player) = &mut self.player {
                    player.controller.process_keyboard(physical_key, state);
                }
                
                if physical_key == winit::keyboard::PhysicalKey::Code(winit::keyboard::KeyCode::Escape) && state == ElementState::Pressed {
                    event_loop.exit();
                }
            }
            WindowEvent::RedrawRequested => {
                if let (Some(context), Some(pipeline)) = (&self.render_context, &self.render_pipeline) {
                    let frame = match context.surface.get_current_texture() {
                        wgpu::CurrentSurfaceTexture::Success(tex) | wgpu::CurrentSurfaceTexture::Suboptimal(tex) => tex,
                        _ => {
                            if let Some(window) = &self.window {
                                window.request_redraw();
                            }
                            return;
                        }
                    };
                    let view = frame
                        .texture
                        .create_view(&wgpu::TextureViewDescriptor::default());
                    let mut encoder =
                        context
                            .device
                            .create_command_encoder(&wgpu::CommandEncoderDescriptor {
                                label: Some("Render Encoder"),
                            });

                    {
                        let mut render_pass =
                            encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                                label: Some("Render Pass"),
                                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                    view: &view,
                                    resolve_target: None,
                                    ops: wgpu::Operations {
                                        load: wgpu::LoadOp::Clear(wgpu::Color {
                                            r: 0.1,
                                            g: 0.2,
                                            b: 0.3,
                                            a: 1.0,
                                        }),
                                        store: wgpu::StoreOp::Store,
                                    },
                                    depth_slice: None,
                                })],
                                depth_stencil_attachment: None,
                                timestamp_writes: None,
                                occlusion_query_set: None,
                                multiview_mask: None,
                            });

                        // Update state
                        let now = std::time::Instant::now();
                        let dt = now - self.last_render_time;
                        self.last_render_time = now;

                        if let (Some(world), Some(player), Some(uniform), Some(buf)) = (&mut self.world, &mut self.player, &mut self.camera_uniform, &self.camera_buffer) {
                            world.update(dt);
                            player.update(dt, world);
                            uniform.update_view_proj(&player.camera, player.get_eye_position(), player.yaw, player.pitch);
                            context.queue.write_buffer(&buf.buffer, 0, bytemuck::cast_slice(&[*uniform]));
                        }

                        render_pass.set_pipeline(&pipeline.pipeline);
                        if let Some(bind_group) = &self.bind_group {
                            render_pass.set_bind_group(0, bind_group, &[]);
                        }
                        
                        for render_data in self.render_chunks.values() {
                            render_pass.set_vertex_buffer(0, render_data.vertex_buffer.buffer.slice(..));
                            render_pass.set_index_buffer(render_data.index_buffer.buffer.slice(..), wgpu::IndexFormat::Uint32);
                            render_pass.draw_indexed(0..render_data.num_indices, 0, 0..1);
                        }
                    }

                    context.queue.submit(std::iter::once(encoder.finish()));
                    frame.present();
                }
                
                // Request next redraw
                if let Some(window) = &self.window {
                    window.request_redraw();
                }
            }
            _ => {}
        }
    }

    fn device_event(
        &mut self,
        _event_loop: &winit::event_loop::ActiveEventLoop,
        _device_id: winit::event::DeviceId,
        event: winit::event::DeviceEvent,
    ) {
        match event {
            winit::event::DeviceEvent::MouseMotion { delta } => {
                if let Some(player) = &mut self.player {
                    player.controller.process_mouse(delta.0, delta.1);
                }
            }
            _ => (),
        }
    }

    fn about_to_wait(&mut self, _event_loop: &winit::event_loop::ActiveEventLoop) {
        if let Some(window) = self.window.as_ref() {
            window.request_redraw();
        }
    }
}

pub fn run() {
    let event_loop = EventLoop::new().unwrap();
    let mut app = App::default();
    event_loop.run_app(&mut app).unwrap();
}
