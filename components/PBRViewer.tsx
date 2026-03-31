"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import {
  Bounds,
  ContactShadows,
  Environment,
  OrbitControls,
  Stage,
  useBounds,
  useGLTF,
} from "@react-three/drei";
import * as THREE from "three";

type PBRViewerProps = {
  glbUrl: string | null;
  /** 새 GLB가 로드될 때마다 증가시켜 입장 연출을 트리거 */
  modelVersion: number;
  autoRotate: boolean;
  className?: string;
};

function FitCamera({ token }: { token: string }) {
  const api = useBounds();
  useEffect(() => {
    void api.refresh().clip().fit();
  }, [api, token]);
  return null;
}

/** Tripo 스타일: 살짝 당겨지는 줌 + 모델 스케일 입장 */
function ViewportIntro({ fire }: { fire: number }) {
  const { camera } = useThree();
  const t = useRef(0);
  useEffect(() => {
    t.current = 0;
    if (fire > 0 && camera instanceof THREE.PerspectiveCamera) {
      camera.zoom = 0.88;
      camera.updateProjectionMatrix();
    }
  }, [fire, camera]);

  useFrame((_, dt) => {
    if (fire === 0 || !(camera instanceof THREE.PerspectiveCamera)) return;
    if (t.current >= 1) return;
    t.current = Math.min(1, t.current + dt * 1.05);
    const e = 1 - Math.pow(1 - t.current, 2.8);
    camera.zoom = THREE.MathUtils.lerp(0.88, 1, e);
    camera.updateProjectionMatrix();
  });
  return null;
}

function ModelEntrance({
  children,
  version,
}: {
  children: ReactNode;
  version: number;
}) {
  const ref = useRef<THREE.Group>(null);
  const t = useRef(0);
  useEffect(() => {
    t.current = 0;
    if (ref.current) ref.current.scale.setScalar(0.78);
  }, [version]);

  useFrame((_, dt) => {
    if (!ref.current) return;
    if (t.current < 1) {
      t.current = Math.min(1, t.current + dt * 1.35);
      const e = 1 - Math.pow(1 - t.current, 2.2);
      const s = 0.78 + 0.22 * e;
      ref.current.scale.setScalar(s);
    }
  });

  return <group ref={ref}>{children}</group>;
}

function PlaceholderBlock() {
  return (
    <mesh castShadow receiveShadow>
      <boxGeometry args={[0.85, 0.85, 0.85]} />
      <meshStandardMaterial
        color="#1e1e22"
        metalness={0.45}
        roughness={0.42}
        envMapIntensity={0.9}
      />
    </mesh>
  );
}

function GlbModel({ url, version }: { url: string; version: number }) {
  const { scene } = useGLTF(url);
  const clone = useMemo(() => scene.clone(true), [scene]);

  useEffect(() => {
    return () => {
      useGLTF.clear(url);
    };
  }, [url]);

  return (
    <ModelEntrance version={version}>
      <primitive object={clone} />
    </ModelEntrance>
  );
}

function Rig({ autoRotate }: { autoRotate: boolean }) {
  return (
    <OrbitControls
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={1.2}
      maxDistance={16}
      autoRotate={autoRotate}
      autoRotateSpeed={0.65}
    />
  );
}

function Scene({
  glbUrl,
  modelVersion,
  autoRotate,
}: {
  glbUrl: string | null;
  modelVersion: number;
  autoRotate: boolean;
}) {
  const { gl } = useThree();
  useEffect(() => {
    gl.toneMapping = THREE.ACESFilmicToneMapping;
    gl.toneMappingExposure = 1;
  }, [gl]);

  const fitToken = glbUrl ? `glb:${glbUrl}:${modelVersion}` : "placeholder";

  return (
    <>
      <color attach="background" args={["#0A0A0A"]} />
      <ambientLight intensity={0.2} />
      <Environment preset="city" />
      <ContactShadows
        position={[0, -1.05, 0]}
        opacity={0.48}
        scale={14}
        blur={2.4}
        far={7}
      />
      <ViewportIntro fire={glbUrl ? modelVersion : 0} />
      <Rig autoRotate={autoRotate} />
      <Bounds fit clip observe margin={1.08}>
        <FitCamera token={fitToken} />
        <Stage
          key={fitToken}
          intensity={0.5}
          shadows={false}
          adjustCamera={1.08}
        >
          {glbUrl ? (
            <Suspense fallback={null}>
              <GlbModel url={glbUrl} version={modelVersion} />
            </Suspense>
          ) : (
            <PlaceholderBlock />
          )}
        </Stage>
      </Bounds>
    </>
  );
}

export function PBRViewer({
  glbUrl,
  modelVersion,
  autoRotate,
  className,
}: PBRViewerProps) {
  const [dpr, setDpr] = useState(1.5);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 640px)");
    const apply = () => setDpr(mq.matches ? 1 : Math.min(2, window.devicePixelRatio));
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  return (
    <div className={className}>
      <Canvas
        shadows
        className="h-full w-full touch-none"
        camera={{ position: [3.6, 1.55, 4.6], fov: 40, near: 0.1, far: 80 }}
        dpr={dpr}
        gl={{ antialias: true, alpha: false }}
      >
        <Suspense fallback={null}>
          <Scene
            glbUrl={glbUrl}
            modelVersion={modelVersion}
            autoRotate={autoRotate}
          />
        </Suspense>
      </Canvas>
    </div>
  );
}
