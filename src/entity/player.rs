use crate::camera::Camera;
use crate::controller::PlayerController;
use crate::entity::Entity;
use glam::Vec3;
use std::time::Duration;

pub struct Player {
    pub position: Vec3,
    pub yaw: f32,
    pub pitch: f32,
    pub camera: Camera,
    pub controller: PlayerController,
}

impl Player {
    pub fn new(position: Vec3, yaw: f32, pitch: f32, aspect: f32) -> Self {
        Self {
            position,
            yaw,
            pitch,
            camera: Camera::new(aspect, std::f32::consts::FRAC_PI_4, 0.1, 1000.0),
            controller: PlayerController::new(4.0, 0.4),
        }
    }
}

impl Entity for Player {
    fn update(&mut self, dt: Duration) {
        let dt = dt.as_secs_f32();

        // Rotation: Mouse delta is discrete, typically not multiplied by dt for standard FPS feel
        // but sensitivity should be tuned.
        self.yaw += self.controller.rotate_horizontal * self.controller.sensitivity * 0.01;
        self.pitch += -self.controller.rotate_vertical * self.controller.sensitivity * 0.01;

        // Reset rotation buffers
        self.controller.rotate_horizontal = 0.0;
        self.controller.rotate_vertical = 0.0;

        // Pitch limits (approx 89 degrees)
        let safe_pitch = std::f32::consts::FRAC_PI_2 - 0.01;
        if self.pitch < -safe_pitch {
            self.pitch = -safe_pitch;
        } else if self.pitch > safe_pitch {
            self.pitch = safe_pitch;
        }

        // Movement
        let (yaw_sin, yaw_cos) = self.yaw.sin_cos();
        let forward = Vec3::new(yaw_cos, 0.0, yaw_sin).normalize();
        let right = Vec3::new(-yaw_sin, 0.0, yaw_cos).normalize();
        
        let mut move_dir = Vec3::ZERO;
        move_dir += forward * (self.controller.amount_forward - self.controller.amount_backward);
        move_dir += right * (self.controller.amount_right - self.controller.amount_left);
        move_dir.y += self.controller.amount_up - self.controller.amount_down;

        if move_dir.length_squared() > 0.0 {
            self.position += move_dir.normalize() * self.controller.speed * dt;
        }
    }

    fn position(&self) -> Vec3 {
        self.position
    }
}
