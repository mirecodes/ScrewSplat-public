# Haven 3D Voxel Engine - Architecture Overview

## 프로젝트 목적
Haven은 초기 마인크래프트 스타일의 복셀(Voxel) 샌드박스 게임을 바닥부터 구현하는 것을 목표로 합니다.
Rust의 안정성과 성능, 그리고 최신 그래픽스 API인 WGPU를 사용하여 플랫폼 독립적으로 동작하는 고성능 엔진을 구축합니다.

## 시스템 아키텍처 (Implementation Frame)

본 프로젝트는 크게 다음과 같은 서브 시스템으로 구성되어 있습니다.

### 1. 애플리케이션 및 이벤트 루프 (App & Winit)
- `winit` 크레이트의 최신 `ApplicationHandler` 패턴을 사용하여 운영체제의 윈도우 생성 및 이벤트를 처리합니다.
- 메인 렌더링 루프(`RedrawRequested`)에서 시간의 흐름(`DeltaTime`)을 계산하고 물리 업데이트와 렌더링을 순차적으로 실행합니다.

### 2. 엔티티-컨트롤러 패턴 (Entity-Controller)
- **제어 로직 분리**: 플레이어의 입력(키보드 WASD, 마우스 이동)은 `PlayerController`가 수집하고 누적합니다.
- **상태 관리**: `Player` 엔티티는 자신의 위치와 시선(Yaw, Pitch)을 가지며, 매 프레임 컨트롤러의 누적된 입력을 바탕으로 자신의 상태를 업데이트합니다.
- **카메라 (Camera)**: 카메라는 상태를 가지지 않고(Stateless), 플레이어의 위치와 시선을 받아 GPU로 전송할 뷰-프로젝션 매트릭스를 계산하는 순수 수학 계산 객체로 동작합니다.

### 3. 월드 및 복셀 시스템 (World & Voxel)
- **Chunk (16x256x16)**: 3D 복셀 데이터는 청크 단위로 분할되어 관리됩니다. 내부는 1차원 배열을 사용하여 캐시 적중률을 높였습니다.
- **World Management**: `World` 구조체는 `HashMap<(i32, i32), Chunk>`를 사용하여 월드 좌표계에 따라 무한히 확장可能な 청크들을 관리합니다.
- **Terrain Generation**: `terrain.rs` 모듈에서 삼각함수 알고리즘을 사용하여 좌표 기반의 동적 지형(돌, 흙, 잔디)을 생성합니다.

### 4. 렌더링 엔진 (WGPU)
- **Context & Pipeline**: WGPU를 통해 Instance -> Adapter -> Device -> Queue 순으로 초기화되며, 셰이더(WGSL)와 바인드 그룹 레이아웃을 포함하는 렌더 파이프라인을 구성합니다.
- **Meshing (Face Culling)**: 각 청크는 공기와 맞닿은 외곽 면(Face)만 버텍스로 생성하는 페이스 컬링(Face Culling) 알고리즘을 통해 그려야 할 폴리곤 수를 극적으로 줄입니다.
- **Texture Atlas**: 하나의 텍스처 파일 안에 여러 블록(잔디, 흙, 돌 등)의 텍스처를 모아두고, 메싱 시 적절한 UV 좌표를 할당하여 단일 드로우 콜로 다양한 블록을 렌더링합니다.
- **Multi-Chunk Rendering**: 청크별로 버텍스/인덱스 버퍼를 각각 소유(`ChunkRenderData`)하며, 가시 범위 내의 모든 청크를 순회하며 렌더링합니다.
