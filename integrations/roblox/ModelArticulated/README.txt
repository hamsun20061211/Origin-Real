Roblox — 관절(다중 Part) 자동차/릭 전체 구동은 HingeConstraint + 바퀴 Part 별 스크립트가 필요합니다.
이 폴더는 "프로토타입 단계": PrimaryPart만 움직이고 나머지는 WeldConstraint로 몸체에 고정했다고 가정합니다.

Studio에서:
1. Model.PrimaryPart = 메인 바디 Part
2. ChaseUsingPrimaryPart.server.lua 를 Model 자식으로 넣기 (이름은 .server.lua 대신 Studio에서 Script로 저장 시 확장자 제거)
