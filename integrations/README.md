# Origin Real → Roblox / Unity 연동 스크립트

GLB 등으로 내보낸 메쉬에 **굴리기 / 플레이어 추적** 물리 프로토타입을 붙일 때 쓰는 파일입니다.

## Roblox

1. 메쉬를 **FBX 등**으로 변환해 Studio에 업로드 (GLB는 Blender 등에서 FBX export 권장).
2. **단일 MeshPart:** `integrations/roblox/SingleMeshPart/` 의 코드를 **Script**로 복사해 MeshPart **자식**에 붙입니다.  
   - 파일명 `.server.lua`는 Rojo용 관례일 뿐이며, Studio에서는 그냥 **Script**에 붙여넣으면 됩니다.
3. **Model + PrimaryPart:** `ModelArticulated/ChaseUsingPrimaryPart` 를 **Model** 자식으로 넣고 `PrimaryPart` 설정.

## Unity

1. `integrations/unity/` 전체를 새 Unity 프로젝트의 `Assets/` 아래 폴더로 복사합니다 (예: `Assets/OriginRealIntegration/`).
2. 생성한 프리팹 **루트**에 `Rigidbody` + `Collider`를 두고, Hierarchy에서 오브젝트 선택.
3. 메뉴 **Tools → Origin Real → Attach → …** 로 `RollForward` / `ChasePlayer` 부착.
4. **Player** 태그가 씬에 있는 플레이어 오브젝트에 붙어 있어야 `ChasePlayer`가 대상을 찾습니다.
5. **바퀴 토크:** 바퀴 파트에 별도 `Rigidbody`가 있다면 그걸 `SimpleWheelTorque.wheelBody`에 드래그.

## 한계

- 관절 리그·애니·NavMesh·WheelCollider 4바퀴 차량은 **엔진 튜토리얼 범위**입니다. 여기서는 **프로토타입 스크립트**만 제공합니다.
