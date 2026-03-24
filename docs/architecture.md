# Haven 3D Voxel Engine - Architecture Overview

## 프로젝트 목적
Haven은 초기 마인크래프트 스타일의 복셀(Voxel) 샌드박스 게임을 바닥부터 구현하는 것을 목표로 합니다.
Rust의 안정성과 성능, 그리고 최신 그래픽스 API인 WGPU를 사용하여 플랫폼 독립적으로 동작하는 고성능 엔진을 구축합니다.

## 시스템 아키텍처 (Implementation Frame)

본 프로젝트는 크게 다음과 같은 서브 시스템으로 구성되어 있습니다.

### 1. 애플리케이션 및 이벤트 루프 (App & Winit)
- `winit` 크레이트의 최신 `ApplicationHandler` 패턴을 사용하여 운영체제의 윈도우 생성 및 이벤트를 처리합니다.
- 메인 렌더링 루프(`RedrawRequested`)에서 시간의 흐름(`DeltaTime`)을 계산하고 물리 업데이트와 렌더링을 순차적으로 실행합니다.
- **물리 분리**: 물리 연산은 일정한 타임스텝 또는 프레임 델타를 사용하여 렌더링과 독립적인 로직을 수행할 수 있도록 설계되었습니다.

### 2. 엔티티-컨트롤러 패턴 (Entity-Controller)
- **제어 로직 분리**: 플레이어의 입력(키보드 WASD, 마우스 이동)은 `PlayerController`가 수집하고 누적합니다.
- **상태 관리**: `Player` 엔티티는 자신의 위치와 시선(Yaw, Pitch)을 가지며, 매 프레임 컨트롤러의 누적된 입력을 바탕으로 자신의 상태를 업데이트합니다.
- **카메라 (Camera)**: 카메라는 상태를 가지지 않고(Stateless), 플레이어의 위치와 시선을 받아 GPU로 전송할 뷰-프로젝션 매트릭스를 계산하는 순수 수학 계산 객체로 동작합니다.

### 3. 월드 및 복셀 시스템 (World & Voxel)
- **Chunk (16x256x16)**: 3D 복셀 데이터는 청크 단위로 분할되어 관리됩니다. 내부는 1차원 배열을 사용하여 캐시 적중률을 높였습니다.
- **World Management**: `World` 구조체는 `HashMap<(i32, i32), Chunk>`를 사용하여 월드 좌표계에 따라 무한히 확장可能な 청크들을 관리합니다.
- **Terrain Generation**: `terrain.rs` 모듈에서 삼각함수 알고리즘을 사용하여 좌표 기반의 동적 지형(돌, 흙, 잔디)을 생성합니다.
- **AABB Collision**: 플레이어와 월드 간의 충돌은 축 정렬 경계 상자(AABB)를 사용하여 처리됩니다. 물리 업데이트 시 Y, X, Z 축 순서로 이동을 시도하며 고체 블록과의 간섭을 확인하여 미끄러짐(Sliding)과 중력을 구현합니다.

### 4. 렌더링 엔진 (WGPU)
- **Context & Pipeline**: WGPU를 통해 Instance -> Adapter -> Device -> Queue 순으로 초기화되며, 셰이더(WGSL)와 바인드 그룹 레이아웃을 포함하는 렌더 파이프라인을 구성합니다.
- **Meshing (Face Culling)**: 각 청크는 공기 또는 인접 청크의 공기와 맞닿은 외곽 면(Face)만 버텍스로 생성하는 페이스 컬링(Face Culling) 알고리즘을 통해 그려야 할 폴리곤 수를 극적으로 줄입니다. (`get_block_global`을 통한 청크 간 경계 처리 포함)
- **Texture Atlas**: 하나의 텍스처 파일 안에 여러 블록(잔디, 흙, 돌 등)의 텍스처를 모아두고, 메싱 시 적절한 UV 좌표를 할당하여 단일 드로우 콜로 다양한 블록을 렌더링합니다.
- **Directional Lighting**: WGSL 셰이더에서 램버트 코사인 법칙을 사용하여 태양광의 방향과 블록 면의 법선 벡터(Normal) 사이의 각도에 따른 음영을 계산합니다. 이를 통해 큐브 지형에 입체감을 부여합니다.
- **Depth Buffer (Z-Buffer)**: `Depth32Float` 포맷의 깊이 텍스처를 사용하여 3D 공간 상의 객체 선후 관계를 정확하게 판별하고 렌더링 순서 문제를 해결합니다.
- **Multi-Chunk Rendering**: 청크별로 버텍스/인덱스 버퍼를 각각 소유(`ChunkRenderData`)하며, 가시 범위 내의 모든 청크를 순회하며 렌더링합니다.

### 5. 동적 청크 관리 및 세이트/로드 (Dynamic World)
- **Background Loading (MPSC)**: 지형 생성과 파일 I/O는 메인 렌더 루프를 방해하지 않도록 별도의 백그라운드 스레드에서 수행됩니다. `World` 객체가 `chunk_receiver`를 통해 생성 완료된 청크를 전달받아 즉시 렌더링 목록에 추가합니다.
- **Serialization & Memory Management**: `serde`와 `bincode`를 사용하여 청크 데이터를 바이너리로 압축 저장합니다. 플레이어 반경 밖으로 벗어난 청크는 디스크에 자동 저장되며 RAM и VRAM 버퍼에서 완전히 해제되어 메모리 누수를 원천 차단합니다.
- **Spawn Sync & Anti-Tunneling**: 최초 스폰 시 반경 내 청크 로드를 확인한 뒤 3초 대기 후 안전하게 지면에 안착시킵니다. 또한 렌더 루프 랙(Lag)이 발생했을 때 델타 타임(`dt`)을 최대 0.1초로 제한하여 1프레임 만에 지면을 관통하는 물리 폭발(Tunneling)을 방지합니다.

### 6. 디버그 및 인터페이스 (GUI)
- **Egui Integration**: `egui-wgpu`를 사용하여 WGPU 프레임 버퍼 위에 즉시 모드(Immediate Mode) UI를 렌더링합니다. 
- **System Monitoring**: 실시간 렌더링 FPS, `sysinfo`를 활용한 CPU/RAM 자원 점유율, 플레이어 좌표 등을 화면 측면에 투명 오버레이로 출력합니다. `F2` 키를 통해 패널을 동적으로 켜고 끌 수 있습니다.
