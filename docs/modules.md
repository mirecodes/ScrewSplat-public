# Haven Modules & File Structure

프로젝트 코드는 기능 단위로 철저하게 모듈화되어 있습니다. 다음은 `src/` 디렉토리 내의 주요 모듈과 파일별 역할입니다.

## 루트 모듈 (`src/`)
- **`main.rs`**: 프로그램 진입점. 로거 초기화 및 `App` 이벤트 루프 구동.
- **`app.rs`**: 핵심 애플리케이션 클래스. `winit` 생명주기 관리, 렌더링 리소스(버퍼, 패스) 초기화, 입력 전달 및 렌더링 루프 조율.
- **`camera.rs`**: `glam` 수학 라이브러리를 사용하여 뷰 매트릭스 및 프로젝션 매트릭스를 계산. Uniform Buffer용 구조체(`CameraUniform`) 정의.
- **`controller.rs`**: 플랫폼 입력을 해석하여 수치화하는 `PlayerController` 정의 (이동, 회전 누적).

## 엔티티 시스템 (`src/entity/`)
- **`mod.rs`**: 모든 게임 객체의 기본이 되는 `Entity` 트레이트 정의.
- **`player.rs`**: 1인칭 플레이어 속성(위치, 눈높이, 시선, 속도) 및 물리/충돌 로직 구현. `Camera`와 `PlayerController` 소유. 카메라는 플레이어의 눈높이(`get_eye_position`)에 맞춰 업데이트됩니다.

## 렌더링 라이브러리 (`src/render/`)
- **`context.rs`**: WGPU 초기화 (Device, Queue, Surface).
- **`pipeline.rs`**: WGSL 셰이더 로드, 포매, 깊이 스텐실 설정(`depth_stencil`) 및 바인드 그룹 레이아웃을 포함하는 렌더 파이프라인 생성.
- **`buffer.rs`**: 버텍스, 인덱스, Uniform 버퍼 생성을 쉽게 해주는 제네릭 래퍼(Wrapper).
- **`texture.rs`**: `image` 크레이트를 이용한 텍스처 아틀라스 생성 및 렌더링/깊이 테스트용 Depth Texture 생성 로직 보유.
- **`light.rs`**: 글로벌 광원 설정을 위한 `LightUniform` 구조체 정의.
- **`shader.wgsl`**: GPU에서 동작하는 버텍스 및 프래그먼트 셰이더 코드. 텍스처 샘플링과 디렉셔널 라이팅 음영 계산 수행.

## 메시 생성기 (`src/mesh/`)
- **`vertex.rs`**: 3D 공간의 버텍스 인터페이스 정의 (위치, UV 좌표, 노멀 벡터).
- **`builder.rs`**: 복셀 데이터를 바탕으로 폴리곤을 생성하는 메셔. 투명하지 않은 블록 간섭면을 최적화하는 Face Culling 구현. 다중 청크 위치 보정을 위해 `world_offset` 반영.

## 월드 데이터 (`src/world/`)
- **`mod.rs`**: `World` 매니저. 엔티티들과 다수의 청크들을 좌표 기반으로 종합 관리. 글로벌 블록 조회(`get_block_global`) 및 AABB 충돌 판정(`has_solid_block_in_aabb`) 기능 제공.
- **`chunk.rs`**: 16x256x16 크기의 실제 복셀 블록 데이터를 1차원 벡터로 보유.
- **`block.rs`**: 블록 종류(`BlockType` Enum - Air, Grass, Dirt, Stone) 및 특성 정의.
- **`terrain.rs`**: 월드/청크 좌표 공간에 따라 절차적으로 블록을 배치하여 자연스러운 지형 변위를 만드는 알고리즘.

## 디버그 및 시스템 (`src/debug.rs`)
- **`SystemMonitor`**: `sysinfo` 라이브러리를 통해 실시간 CPU 및 RAM 점유율을 계산하고 적절한 쿨다운 타이밍으로 정보를 갱신하는 모듈.
