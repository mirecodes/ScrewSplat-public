use glam::{Mat4, Vec3};

pub struct Camera {
    pub aspect: f32,
    pub fovy: f32,
    pub znear: f32,
    pub zfar: f32,
}

impl Camera {
    pub fn new(aspect: f32, fovy: f32, znear: f32, zfar: f32) -> Self {
        Self {
            aspect,
            fovy,
            znear,
            zfar,
        }
    }

    pub fn build_view_projection_matrix(&self, position: Vec3, yaw: f32, pitch: f32) -> Mat4 {
        let (sin_pitch, cos_pitch) = pitch.sin_cos();
        let (sin_yaw, cos_yaw) = yaw.sin_cos();

        let forward = Vec3::new(cos_pitch * cos_yaw, sin_pitch, cos_pitch * sin_yaw).normalize();
        let right = Vec3::new(-sin_yaw, 0.0, cos_yaw).normalize();
        let up = right.cross(forward).normalize();

        let view = Mat4::look_at_rh(position, position + forward, up);
        let proj = Mat4::perspective_rh(self.fovy, self.aspect, self.znear, self.zfar);

        proj * view
    }
}

#[repr(C)]
#[derive(Debug, Copy, Clone, bytemuck::Pod, bytemuck::Zeroable)]
pub struct CameraUniform {
    pub view_proj: [[f32; 4]; 4],
}

impl CameraUniform {
    pub fn new() -> Self {
        Self {
            view_proj: Mat4::IDENTITY.to_cols_array_2d(),
        }
    }

    pub fn update_view_proj(&mut self, camera: &Camera, position: Vec3, yaw: f32, pitch: f32) {
        self.view_proj = camera.build_view_projection_matrix(position, yaw, pitch).to_cols_array_2d();
    }
}
