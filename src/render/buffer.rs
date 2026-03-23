pub struct Buffer<T> {
    pub buffer: wgpu::Buffer,
    pub len: usize,
    _marker: std::marker::PhantomData<T>,
}

impl<T: bytemuck::Pod> Buffer<T> {
    pub fn new_vertex(device: &wgpu::Device, data: &[T]) -> Self {
        use wgpu::util::DeviceExt;
        let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Vertex Buffer"),
            contents: bytemuck::cast_slice(data),
            usage: wgpu::BufferUsages::VERTEX | wgpu::BufferUsages::COPY_DST,
        });

        Self {
            buffer,
            len: data.len(),
            _marker: std::marker::PhantomData,
        }
    }

    pub fn new_index(device: &wgpu::Device, data: &[u32]) -> Buffer<u32> {
        use wgpu::util::DeviceExt;
        let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Index Buffer"),
            contents: bytemuck::cast_slice(data),
            usage: wgpu::BufferUsages::INDEX | wgpu::BufferUsages::COPY_DST,
        });

        Buffer {
            buffer,
            len: data.len(),
            _marker: std::marker::PhantomData,
        }
    }

    pub fn new_uniform(device: &wgpu::Device, data: &[T]) -> Self {
        use wgpu::util::DeviceExt;
        let buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Uniform Buffer"),
            contents: bytemuck::cast_slice(data),
            usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
        });

        Self {
            buffer,
            len: data.len(),
            _marker: std::marker::PhantomData,
        }
    }
}
