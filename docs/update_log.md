# Update Log

## [v0.1.0] - Phase 2 Completion

초기 3D 엔진 구성 및 확장을 위한 시스템 아키텍처 개편 작업 완료.

### Step 1 & 2: 기반 렌더링 및 모듈화 설계
- WGPU 기반 기초 렌더링 컨텍스트 및 파이프라인 구성.
- `winit` 0.30 이벤트 프레임워크 연동.
- 텍스처 아틀라스 생성 및 셰이더 UV 매핑 구현.

### Step 3: 엔티티-컨트롤러 패턴 적용 및 1인칭 조작
- 카메라에서 가변 상태를 제거하고 수학 유틸리티로 리팩토링 (`camera.rs`).
- 키보드/마우스 입력을 제어하는 `PlayerController` 추가.
- `dt`(DeltaTime) 기반의 물리 갱신 방식을 사용하는 `Player` 엔티티 구현.
- 게임 창 캡처 및 화면 내 마우스 가두기(`CursorGrabMode`) 적용.

### Step 4 & 5: 월드 매니저와 다중 청크 시스템 구축
- 16x256x16 크기의 단일 Chunk에서 무한 확장을 염두에 둔 `World` 객체 도입.
- 공간 해시맵(`HashMap<(i32, i32), Chunk>`)을 이용해 가상의 다중 청크 관리 도입.
- 다중 청크의 버텍스 오프셋을 조절해 이어지는 메싱 작성 구현 (`mesh/builder.rs`).
- `App` 모듈에서 3x3 크기의 주변 청크를 초기에 한시 생성 및 개별 렌더 버퍼 배정, 다중 그리기(Draw Call) 수행 구현.
- X, Z 좌표에 따라 굴곡진 지형이 형성되는 절차적 지형 생성기 마련 (`world/terrain.rs`).

## [v0.2.0] - Phase 3 Completion

물리 충돌 엔진 및 조명 시스템 구현을 통한 게임 플레이 경험 고도화.

### Step 1: 청크 경계 컬링 최적화
- `World::get_block_global` 구현으로 인접 청크 데이터 참조 가능화.
- 청크 경계면에서 중복 면 생성 방지 및 시각적 노이즈 제거.

### Step 2: AABB 물리 및 충돌 시스템
- 플레이어에게 중력 적용 및 `velocity` 기반 이동 체계 구축.
- 축별 분리 충돌 검사로 블록과의 정교한 물리 충돌 및 미끄러짐 구현.

### Step 3: 디렉셔널 라이팅 및 음영 셰이더
- `LightUniform` 및 법선 벡터(Normal)를 이용한 광원 시스템 구축.
- 램버트 코사인 법칙을 적용하여 블록의 방향에 따른 입체적 음영 표현.

### Step 4: Depth Buffer (Z-Buffer) 및 물리 보정
- `Depth32Float` 포맷의 깊이 버퍼를 도입하여 렌더링 순서 오류 및 관통 문제 해결.
- 플레이어 카메라 위치를 눈높이(Eye Level)로 조정하여 1인칭 시점 안정화.


## [v0.3.0] - Phase 4 Completion

동적 청크 관리와 파일 기반 세이브/로드 시스템 구축.

### Step 1: Serialization & Compression
- `serde`, `bincode`, `flate2`를 연동하여 청크 데이터를 바이너리로 압축 저장 및 로드 구현.
- `Chunk` 구조체에 시리얼라이즈 필드 추가 및 데이터 변환 로직 마련.

### Step 2: Dynamic Chunk Manager
- 플레이어 주위 반경(Radius) 기반의 청크 로딩 알고리즘 구현.
- 일정 거리를 벗어난 청크는 자동 서드파티 저장 및 RAM/VRAM 완전 언로드(Unload)를 통한 메모리 누수 방지.
- 최초 접속 시 주변 청크 로드 확인 및 3초 지연 안착 로직을 통해 초기 무한 추락(Tunneling) 버그 완벽 해결.

### Step 3: Background Processing (MPSC Threads)
- 메인 렌더 루프 블로킹 방지를 위한 `std::sync::mpsc` 기반 비동기 청크 생성/로딩 스레드 구현.
- 백그라운드에서 지형 생성이 완료되면 채널을 통해 메인 스레드로 전달하여 즉각 렌더링 반영.

## [v0.4.0] - Phase 5 Completion

Egui 기반 디버그 UI 및 시스템 리소스 모니터링 통합.

### Step 1: Egui & Sysinfo Integration
- `egui-winit`, `egui-wgpu`를 이용한 WGPU 환경 내 UI 레이어 통합.
- `sysinfo` 크레이트를 통해 CPU, RAM 사용량을 실시간으로 수집하는 `SystemMonitor` 구조체 구현.

### Step 2: Debug Overlay Implementation
- `F2` 키를 이용한 디버그 패널 토글 기능 추가.
- 실시간 렌더링 FPS, 플레이어 좌표, 로드된 청크 수, 시스템 자원(CPU/RAM)을 투명 오버레이로 출력.
- `wgpu` 23.0 버전 호환성 확보 및 `forget_lifetime()`을 이용한 렌더 패스 수명 관리 문제 해결.

---

