use crate::camera::Camera;
use crate::controller::PlayerController;
use crate::entity::Entity;
use glam::Vec3;
use std::time::Duration;

pub struct Player {
    pub position: Vec3,
    pub velocity: Vec3,
    pub yaw: f32,
    pub pitch: f32,
    pub camera: Camera,
    pub controller: PlayerController,
    pub on_ground: bool,
    pub eye_height: f32,
    pub is_spawned: bool,
    pub spawn_timer: f32,
}

impl Player {
    pub fn new(position: Vec3, yaw: f32, pitch: f32, aspect: f32) -> Self {
        Self {
            position,
            velocity: Vec3::ZERO,
            yaw,
            pitch,
            camera: Camera::new(aspect, std::f32::consts::FRAC_PI_4, 0.1, 1000.0),
            controller: PlayerController::new(4.0, 0.4),
            on_ground: false,
            eye_height: 1.6,
            is_spawned: false,
            spawn_timer: 0.0,
        }
    }

    pub fn get_eye_position(&self) -> Vec3 {
        self.position + Vec3::new(0.0, self.eye_height, 0.0)
    }
}

impl Entity for Player {
    fn update(&mut self, dt: Duration, world: &crate::world::World) {
        let mut dt = dt.as_secs_f32();
        if dt > 0.1 {
            dt = 0.1; // Cap dt to prevent tunneling during lag spikes
        }

        // Rotation
        self.yaw += self.controller.rotate_horizontal * self.controller.sensitivity * 0.01;
        self.pitch += -self.controller.rotate_vertical * self.controller.sensitivity * 0.01;

        // Reset rotation buffers
        self.controller.rotate_horizontal = 0.0;
        self.controller.rotate_vertical = 0.0;

        // Pitch limits
        let safe_pitch = std::f32::consts::FRAC_PI_2 - 0.01;
        self.pitch = self.pitch.clamp(-safe_pitch, safe_pitch);

        // Wait for initial spawn area to load (radius 8 to match default render_distance, or 12 if preferred)
        let spawn_radius = world.render_distance; 
        if !self.is_spawned {
            if world.is_area_loaded(self.position.x, self.position.z, spawn_radius) {
                self.spawn_timer += dt;
                if self.spawn_timer >= 3.0 {
                    self.is_spawned = true;
                    // Spawn safely on the highest block
                    self.position.y = world.get_highest_block_y(self.position.x, self.position.z) + self.eye_height;
                } else {
                    self.velocity = Vec3::ZERO;
                    return; // Wait 3 seconds
                }
            } else {
                self.spawn_timer = 0.0; // Reset if unloaded
                self.velocity = Vec3::ZERO;
                return; // Pause physics
            }
        }

        // Additional safety: Pause physics if the chunks intersecting the player's AABB are not loaded
        let half_w = 0.3;
        let p_min = Vec3::new(self.position.x - half_w, self.position.y, self.position.z - half_w);
        let p_max = Vec3::new(self.position.x + half_w, self.position.y + 1.8, self.position.z + half_w);
        let cx_min = (p_min.x.floor() as i32).div_euclid(16);
        let cx_max = (p_max.x.ceil() as i32).div_euclid(16);
        let cz_min = (p_min.z.floor() as i32).div_euclid(16);
        let cz_max = (p_max.z.ceil() as i32).div_euclid(16);
        
        for cx in cx_min..=cx_max {
            for cz in cz_min..=cz_max {
                if !world.chunks.contains_key(&(cx, cz)) {
                    self.velocity = Vec3::ZERO;
                    return;
                }
            }
        }

        // Movement input
        let (yaw_sin, yaw_cos) = self.yaw.sin_cos();
        let forward = Vec3::new(yaw_cos, 0.0, yaw_sin).normalize();
        let right = Vec3::new(-yaw_sin, 0.0, yaw_cos).normalize();
        
        let mut move_dir = Vec3::ZERO;
        move_dir += forward * (self.controller.amount_forward - self.controller.amount_backward);
        move_dir += right * (self.controller.amount_right - self.controller.amount_left);
        
        if move_dir.length_squared() > 0.0 {
            move_dir = move_dir.normalize();
        }

        // Horizontal velocity
        self.velocity.x = move_dir.x * self.controller.speed;
        self.velocity.z = move_dir.z * self.controller.speed;

        // Gravity
        let gravity = 30.0;
        self.velocity.y -= gravity * dt;

        // Jump
        if self.on_ground && self.controller.amount_up > 0.0 {
            self.velocity.y = 10.0;
            self.on_ground = false;
        }

        // Apply movement with collision
        let player_box_half_width = 0.3;
        let player_height = 1.8;

        // Axis-separated movement and collision
        // Y-axis first (for landing)
        self.position.y += self.velocity.y * dt;
        if self.check_collision(world, player_box_half_width, player_height) {
            if self.velocity.y < 0.0 {
                self.on_ground = true;
            }
            self.position.y -= self.velocity.y * dt;
            self.velocity.y = 0.0;
        } else {
            self.on_ground = false;
        }

        // X-axis
        self.position.x += self.velocity.x * dt;
        if self.check_collision(world, player_box_half_width, player_height) {
            self.position.x -= self.velocity.x * dt;
        }

        // Z-axis
        self.position.z += self.velocity.z * dt;
        if self.check_collision(world, player_box_half_width, player_height) {
            self.position.z -= self.velocity.z * dt;
        }
    }

    fn position(&self) -> Vec3 {
        self.position
    }
}

impl Player {
    fn check_collision(&self, world: &crate::world::World, half_w: f32, h: f32) -> bool {
        let min = Vec3::new(self.position.x - half_w, self.position.y, self.position.z - half_w);
        let max = Vec3::new(self.position.x + half_w, self.position.y + h, self.position.z + half_w);
        world.has_solid_block_in_aabb(min, max)
    }
}

