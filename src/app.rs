use winit::{
    application::ApplicationHandler,
    event::*,
    event_loop::{ActiveEventLoop, EventLoop},
    window::{Window, WindowId},
};
use std::sync::Arc;
use std::collections::HashMap;
use glam::Vec3;
use winit::window::CursorGrabMode;

use crate::render::{context::WgpuContext, pipeline::{RenderPipeline, ChunkRenderData}, buffer::Buffer, texture::Texture};
use crate::camera::CameraUniform;
use crate::entity::Entity;
use crate::entity::player::Player;
use crate::world::World;
use crate::render::light::LightUniform;
use crate::mesh::builder::build_chunk_mesh;

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
    depth_texture: Option<Texture>,
    bind_group: Option<wgpu::BindGroup>,
    
    // Debug UI
    egui_ctx: egui::Context,
    egui_state: Option<egui_winit::State>,
    egui_renderer: Option<egui_wgpu::Renderer>,
    show_debug_ui: bool,
    sys_monitor: crate::debug::SystemMonitor,
    
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
            depth_texture: None,
            bind_group: None,
            egui_ctx: egui::Context::default(),
            egui_state: None,
            egui_renderer: None,
            show_debug_ui: true,
            sys_monitor: crate::debug::SystemMonitor::new(),
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
            
            let world = World::new();
            
            let aspect = context.config.width as f32 / context.config.height as f32;
            let player = Player::new((8.0, 80.0, 8.0).into(), -std::f32::consts::FRAC_PI_2, -0.8, aspect);
            let mut camera_uniform = CameraUniform::new();
            camera_uniform.update_view_proj(&player.camera, player.position, player.yaw, player.pitch);
            let camera_buffer = Buffer::new_uniform(&context.device, &[camera_uniform]);
            
            let light_uniform = LightUniform::new([-0.5, -1.0, -0.3], [1.0, 1.0, 1.0], 0.3);
            let light_buffer = Buffer::new_uniform(&context.device, &[light_uniform]);
            
            let texture = Texture::generate_atlas(&context.device, &context.queue);
            let depth_texture = Texture::create_depth_texture(&context.device, &context.config, "depth_texture");
            
            let bind_group = context.device.create_bind_group(&wgpu::BindGroupDescriptor {
                layout: &pipeline.bind_group_layout,
                entries: &[
                    wgpu::BindGroupEntry { binding: 0, resource: camera_buffer.buffer.as_entire_binding() },
                    wgpu::BindGroupEntry { binding: 1, resource: wgpu::BindingResource::TextureView(&texture.view) },
                    wgpu::BindGroupEntry { binding: 2, resource: wgpu::BindingResource::Sampler(&texture.sampler) },
                    wgpu::BindGroupEntry { binding: 3, resource: light_buffer.buffer.as_entire_binding() },
                ],
                label: Some("Main Bind Group"),
            });
            
            window.set_cursor_grab(CursorGrabMode::Confined)
                .or_else(|_| window.set_cursor_grab(CursorGrabMode::Locked))
                .unwrap_or(());
            window.set_cursor_visible(false);

            let egui_state = egui_winit::State::new(
                self.egui_ctx.clone(),
                self.egui_ctx.viewport_id(),
                &window,
                Some(window.scale_factor() as f32),
                None,
                None,
            );
            let egui_renderer = egui_wgpu::Renderer::new(
                &context.device,
                context.config.format,
                None,
                1,
                false,
            );

            self.render_pipeline = Some(pipeline);
            self.render_context = Some(context);
            self.world = Some(world);
            self.player = Some(player);
            self.camera_uniform = Some(camera_uniform);
            self.camera_buffer = Some(camera_buffer);
            self.light_uniform = Some(light_uniform);
            self.light_buffer = Some(light_buffer);
            self.depth_texture = Some(depth_texture);
            self.bind_group = Some(bind_group);
            self.egui_state = Some(egui_state);
            self.egui_renderer = Some(egui_renderer);
            self.last_render_time = std::time::Instant::now();
        }
    }

    fn window_event(&mut self, event_loop: &ActiveEventLoop, _window_id: WindowId, event: WindowEvent) {
        if let Some(state) = &mut self.egui_state {
            let response = state.on_window_event(self.window.as_ref().unwrap(), &event);
            if response.consumed { return; }
        }

        match event {
            WindowEvent::CloseRequested => event_loop.exit(),
            WindowEvent::Resized(physical_size) => {
                if let Some(context) = &mut self.render_context {
                    context.resize(physical_size);
                    self.depth_texture = Some(Texture::create_depth_texture(&context.device, &context.config, "depth_texture"));
                }
            }
            WindowEvent::KeyboardInput { event: KeyEvent { physical_key, state, .. }, .. } => {
                if let Some(player) = &mut self.player {
                    player.controller.process_keyboard(physical_key, state);
                }
                if physical_key == winit::keyboard::PhysicalKey::Code(winit::keyboard::KeyCode::Escape) && state == ElementState::Pressed {
                    event_loop.exit();
                }
                if physical_key == winit::keyboard::PhysicalKey::Code(winit::keyboard::KeyCode::F2) && state == ElementState::Pressed {
                    self.show_debug_ui = !self.show_debug_ui;
                }
            }
            WindowEvent::RedrawRequested => {
                if let (Some(context), Some(pipeline)) = (&self.render_context, &self.render_pipeline) {
                    let frame = match context.surface.get_current_texture() {
                        Ok(tex) => tex,
                        _ => { self.window.as_ref().unwrap().request_redraw(); return; }
                    };
                    let view = frame.texture.create_view(&wgpu::TextureViewDescriptor::default());
                    
                    let now = std::time::Instant::now();
                    let dt = now - self.last_render_time;
                    self.last_render_time = now;

                    // Update
                    if let (Some(world), Some(player), Some(uniform), Some(buf)) = (&mut self.world, &mut self.player, &mut self.camera_uniform, &self.camera_buffer) {
                        world.update(dt);
                        world.update_chunks_around_player(player.position);
                        while let Ok((cx, cz, chunk)) = world.chunk_receiver.try_recv() {
                            world.loading_chunks.remove(&(cx, cz));
                            let mesh = build_chunk_mesh(&chunk, cx, cz, |x, y, z| world.get_block_global(x, y, z));
                            let render_data = ChunkRenderData::new(context, &mesh);
                            self.render_chunks.insert((cx, cz), render_data);
                            world.chunks.insert((cx, cz), chunk);
                        }
                        player.update(dt, world);
                        uniform.update_view_proj(&player.camera, player.get_eye_position(), player.yaw, player.pitch);
                        context.queue.write_buffer(&buf.buffer, 0, bytemuck::cast_slice(&[*uniform]));
                    }

                    // Egui logic
                    let mut egui_output = None;
                    if self.show_debug_ui {
                        if let (Some(state), Some(window)) = (&mut self.egui_state, &self.window) {
                            self.sys_monitor.update();
                            let raw_input = state.take_egui_input(window);
                            self.egui_ctx.begin_pass(raw_input);
                            egui::Window::new("Debug")
                                .anchor(egui::Align2::RIGHT_TOP, egui::vec2(-10.0, 10.0))
                                .frame(egui::Frame::none().fill(egui::Color32::from_black_alpha(150)))
                                .show(&self.egui_ctx, |ui| {
                                    ui.visuals_mut().override_text_color = Some(egui::Color32::WHITE);
                                    if let Some(player) = &self.player {
                                        ui.label(format!("POS: {:.2}, {:.2}, {:.2}", player.position.x, player.position.y, player.position.z));
                                    }
                                    if let Some(world) = &self.world {
                                        ui.label(format!("Chunks: {}", world.chunks.len()));
                                    }
                                    ui.add_space(5.0);
                                    ui.label("System Resources:");
                                    ui.horizontal(|ui| {
                                        ui.label("CPU");
                                        ui.add(egui::ProgressBar::new(self.sys_monitor.cpu_usage() / 100.0).text(format!("{:.1}%", self.sys_monitor.cpu_usage())));
                                    });
                                    ui.horizontal(|ui| {
                                        ui.label("RAM");
                                        ui.add(egui::ProgressBar::new(self.sys_monitor.mem_usage() / 100.0).text(format!("{:.1}%", self.sys_monitor.mem_usage())));
                                    });
                                });
                            egui_output = Some(self.egui_ctx.end_pass());
                        }
                    }

                    // Render
                    let mut encoder = context.device.create_command_encoder(&wgpu::CommandEncoderDescriptor { label: Some("Render Encoder") });
                    {
                        let mut rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                            label: Some("3D Pass"),
                            color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                view: &view,
                                resolve_target: None,
                                ops: wgpu::Operations { load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.1, g: 0.2, b: 0.3, a: 1.0 }), store: wgpu::StoreOp::Store },
                            })],
                            depth_stencil_attachment: Some(wgpu::RenderPassDepthStencilAttachment {
                                view: &self.depth_texture.as_ref().unwrap().view,
                                depth_ops: Some(wgpu::Operations { load: wgpu::LoadOp::Clear(1.0), store: wgpu::StoreOp::Store }),
                                stencil_ops: None,
                            }),
                            timestamp_writes: None,
                            occlusion_query_set: None,
                        });
                        rpass.set_pipeline(&pipeline.pipeline);
                        if let Some(bg) = &self.bind_group { rpass.set_bind_group(0, bg, &[]); }
                        for rd in self.render_chunks.values() {
                            rpass.set_vertex_buffer(0, rd.vertex_buffer.buffer.slice(..));
                            rpass.set_index_buffer(rd.index_buffer.buffer.slice(..), wgpu::IndexFormat::Uint32);
                            rpass.draw_indexed(0..rd.num_indices, 0, 0..1);
                        }
                    }

                    if let (Some(output), Some(renderer), Some(window), Some(state)) = (egui_output, &mut self.egui_renderer, &self.window, &mut self.egui_state) {
                        state.handle_platform_output(window, output.platform_output);
                        let paint_jobs = self.egui_ctx.tessellate(output.shapes, output.pixels_per_point);
                        let sd = egui_wgpu::ScreenDescriptor { size_in_pixels: [context.config.width, context.config.height], pixels_per_point: window.scale_factor() as f32 };
                        for (id, delta) in &output.textures_delta.set { renderer.update_texture(&context.device, &context.queue, *id, delta); }
                        renderer.update_buffers(&context.device, &context.queue, &mut encoder, &paint_jobs, &sd);
                        {
                            let rpass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                                label: Some("Egui Pass"),
                                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                                    view: &view,
                                    resolve_target: None,
                                    ops: wgpu::Operations { load: wgpu::LoadOp::Load, store: wgpu::StoreOp::Store },
                                })],
                                depth_stencil_attachment: None,
                                timestamp_writes: None,
                                occlusion_query_set: None,
                            });
                            let mut rpass = rpass.forget_lifetime();
                            renderer.render(&mut rpass, &paint_jobs, &sd);
                        }
                        for id in &output.textures_delta.free { renderer.free_texture(id); }
                    }

                    context.queue.submit(std::iter::once(encoder.finish()));
                    frame.present();
                }
                self.window.as_ref().unwrap().request_redraw();
            }
            _ => (),
        }
    }

    fn device_event(&mut self, _loop: &ActiveEventLoop, _id: DeviceId, event: DeviceEvent) {
        if let DeviceEvent::MouseMotion { delta } = event {
            if let Some(player) = &mut self.player { player.controller.process_mouse(delta.0, delta.1); }
        }
    }
}

pub fn run() {
    let event_loop = EventLoop::new().unwrap();
    let mut app = App::default();
    event_loop.run_app(&mut app).unwrap();
}
