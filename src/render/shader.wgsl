struct CameraUniform {
    view_proj: mat4x4<f32>,
};

struct LightUniform {
    direction: vec3<f32>,
    color: vec3<f32>,
    ambient_intensity: f32,
};

@group(0) @binding(0)
var<uniform> camera: CameraUniform;

@group(0) @binding(1)
var t_diffuse: texture_2d<f32>;
@group(0) @binding(2)
var s_diffuse: sampler;

@group(0) @binding(3)
var<uniform> light: LightUniform;

struct VertexInput {
    @location(0) position: vec3<f32>,
    @location(1) tex_coords: vec2<f32>,
    @location(2) normal: vec3<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) tex_coords: vec2<f32>,
    @location(1) normal: vec3<f32>,
};

@vertex
fn vs_main(
    model: VertexInput,
) -> VertexOutput {
    var out: VertexOutput;
    out.tex_coords = model.tex_coords;
    out.clip_position = camera.view_proj * vec4<f32>(model.position, 1.0);
    out.normal = model.normal;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let object_color = textureSample(t_diffuse, s_diffuse, in.tex_coords);
    
    let ambient_color = object_color.rgb * light.ambient_intensity;
    
    // Lighting calculation (Lambertian)
    // light.direction is the direction of the light, so we use -light.direction for the vector to the light
    let diffuse_strength = max(dot(normalize(in.normal), normalize(-light.direction)), 0.0);
    let diffuse_color = light.color * diffuse_strength * object_color.rgb;
    
    let result = ambient_color + diffuse_color;
    
    return vec4<f32>(result, object_color.a);
}
