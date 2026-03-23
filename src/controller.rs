use winit::event::*;
use winit::keyboard::{KeyCode, PhysicalKey};

pub struct PlayerController {
    pub speed: f32,
    pub sensitivity: f32,
    pub amount_left: f32,
    pub amount_right: f32,
    pub amount_forward: f32,
    pub amount_backward: f32,
    pub amount_up: f32,
    pub amount_down: f32,
    pub rotate_horizontal: f32,
    pub rotate_vertical: f32,
}

impl PlayerController {
    pub fn new(speed: f32, sensitivity: f32) -> Self {
        Self {
            speed,
            sensitivity,
            amount_left: 0.0,
            amount_right: 0.0,
            amount_forward: 0.0,
            amount_backward: 0.0,
            amount_up: 0.0,
            amount_down: 0.0,
            rotate_horizontal: 0.0,
            rotate_vertical: 0.0,
        }
    }

    pub fn process_keyboard(&mut self, key: PhysicalKey, state: ElementState) -> bool {
        let amount = if state == ElementState::Pressed { 1.0 } else { 0.0 };
        match key {
            PhysicalKey::Code(KeyCode::KeyW) => {
                self.amount_forward = amount;
                true
            }
            PhysicalKey::Code(KeyCode::KeyS) => {
                self.amount_backward = amount;
                true
            }
            PhysicalKey::Code(KeyCode::KeyA) => {
                self.amount_left = amount;
                true
            }
            PhysicalKey::Code(KeyCode::KeyD) => {
                self.amount_right = amount;
                true
            }
            PhysicalKey::Code(KeyCode::Space) => {
                self.amount_up = amount;
                true
            }
            PhysicalKey::Code(KeyCode::ShiftLeft) => {
                self.amount_down = amount;
                true
            }
            _ => false,
        }
    }

    pub fn process_mouse(&mut self, mouse_dx: f64, mouse_dy: f64) {
        self.rotate_horizontal += mouse_dx as f32;
        self.rotate_vertical += mouse_dy as f32;
    }
}
