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
        }
    }

    pub fn get_eye_position(&self) -> Vec3 {
        self.position + Vec3::new(0.0, self.eye_height, 0.0)
    }
}

impl Entity for Player {
    fn update(&mut self, dt: Duration, world: &crate::world::World) {
        let dt = dt.as_secs_f32();

        // Rotation
        self.yaw += self.controller.rotate_horizontal * self.controller.sensitivity * 0.01;
        self.pitch += -self.controller.rotate_vertical * self.controller.sensitivity * 0.01;

        // Reset rotation buffers
        self.controller.rotate_horizontal = 0.0;
        self.controller.rotate_vertical = 0.0;

        // Pitch limits
        let safe_pitch = std::f32::consts::FRAC_PI_2 - 0.01;
        self.pitch = self.pitch.clamp(-safe_pitch, safe_pitch);

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

