/**
 * PointCloudViewer — 3D 点云查看器组件
 * 使用 Three.js 渲染 PLY 点云文件
 */
import { useEffect, useRef, useState, useCallback } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

export interface PointCloudViewerProps {
  url: string;
  width?: number | string;
  height?: number | string;
  backgroundColor?: string;
  pointSize?: number;
  onLoad?: () => void;
  onError?: (error: Error) => void;
  onProgress?: (progress: number) => void;
}

export function PointCloudViewer({
  url,
  width = "100%",
  height = 400,
  backgroundColor = "#1a1a2e",
  pointSize = 0.01,
  onLoad,
  onError,
  onProgress,
}: PointCloudViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);
  const animationIdRef = useRef<number | null>(null);
  
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pointCount, setPointCount] = useState<number>(0);

  // 初始化 Three.js 场景
  const initScene = useCallback(() => {
    if (!containerRef.current) return;
    
    const container = containerRef.current;
    const rect = container.getBoundingClientRect();
    const w = rect.width || 800;
    const h = typeof height === "number" ? height : 400;

    // 场景
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(backgroundColor);
    sceneRef.current = scene;

    // 相机
    const camera = new THREE.PerspectiveCamera(60, w / h, 0.01, 1000);
    camera.position.set(2, 2, 2);
    cameraRef.current = camera;

    // 渲染器
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(w, h);
    renderer.setPixelRatio(window.devicePixelRatio);
    container.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // 控制器
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.screenSpacePanning = true;
    controlsRef.current = controls;

    // 灯光
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(5, 5, 5);
    scene.add(directionalLight);

    // 坐标轴辅助
    const axesHelper = new THREE.AxesHelper(1);
    scene.add(axesHelper);

    // 网格辅助
    const gridHelper = new THREE.GridHelper(4, 20, 0x444444, 0x222222);
    scene.add(gridHelper);

    // 渲染循环
    const animate = () => {
      animationIdRef.current = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();
  }, [backgroundColor, height]);

  // 加载 PLY 文件
  const loadPLY = useCallback(() => {
    if (!sceneRef.current) return;

    const loader = new PLYLoader();
    
    loader.load(
      url,
      (geometry) => {
        // 移除旧的点云
        if (pointsRef.current && sceneRef.current) {
          sceneRef.current.remove(pointsRef.current);
          pointsRef.current.geometry.dispose();
          (pointsRef.current.material as THREE.Material).dispose();
        }

        // 居中几何体
        geometry.computeBoundingBox();
        geometry.center();

        // 计算点数
        const count = geometry.attributes.position?.count ?? 0;
        setPointCount(count);

        // 材质
        const material = new THREE.PointsMaterial({
          size: pointSize,
          vertexColors: geometry.hasAttribute("color"),
          sizeAttenuation: true,
        });

        // 如果没有颜色，使用默认颜色
        if (!geometry.hasAttribute("color")) {
          material.color = new THREE.Color(0x00ffff);
        }

        // 创建点云
        const points = new THREE.Points(geometry, material);
        pointsRef.current = points;
        sceneRef.current!.add(points);

        // 调整相机位置
        if (cameraRef.current && geometry.boundingBox) {
          const box = geometry.boundingBox;
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);
          const distance = maxDim * 2;
          cameraRef.current.position.set(distance, distance, distance);
          cameraRef.current.lookAt(0, 0, 0);
          if (controlsRef.current) {
            controlsRef.current.target.set(0, 0, 0);
            controlsRef.current.update();
          }
        }

        setLoading(false);
        onLoad?.();
      },
      (xhr) => {
        if (xhr.lengthComputable) {
          const progress = (xhr.loaded / xhr.total) * 100;
          onProgress?.(progress);
        }
      },
      (err) => {
        const error = err instanceof Error ? err : new Error("Failed to load PLY file");
        setError(error.message);
        setLoading(false);
        onError?.(error);
      }
    );
  }, [url, pointSize, onLoad, onError, onProgress]);

  // 处理窗口大小变化
  const handleResize = useCallback(() => {
    if (!containerRef.current || !cameraRef.current || !rendererRef.current) return;
    
    const rect = containerRef.current.getBoundingClientRect();
    const w = rect.width;
    const h = typeof height === "number" ? height : rect.height;
    
    cameraRef.current.aspect = w / h;
    cameraRef.current.updateProjectionMatrix();
    rendererRef.current.setSize(w, h);
  }, [height]);

  // 重置视角
  const resetView = useCallback(() => {
    if (cameraRef.current && controlsRef.current) {
      cameraRef.current.position.set(2, 2, 2);
      controlsRef.current.target.set(0, 0, 0);
      controlsRef.current.update();
    }
  }, []);

  // 初始化
  useEffect(() => {
    initScene();
    
    window.addEventListener("resize", handleResize);
    
    return () => {
      window.removeEventListener("resize", handleResize);
      
      if (animationIdRef.current) {
        cancelAnimationFrame(animationIdRef.current);
      }
      
      if (rendererRef.current && containerRef.current) {
        containerRef.current.removeChild(rendererRef.current.domElement);
        rendererRef.current.dispose();
      }
      
      if (pointsRef.current) {
        pointsRef.current.geometry.dispose();
        (pointsRef.current.material as THREE.Material).dispose();
      }
    };
  }, [initScene, handleResize]);

  // 加载文件
  useEffect(() => {
    if (sceneRef.current && url) {
      setLoading(true);
      setError(null);
      loadPLY();
    }
  }, [url, loadPLY]);

  return (
    <div className="pointcloud-viewer" style={{ position: "relative", width, height }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      
      {/* 加载指示器 */}
      {loading && (
        <div className="viewer-overlay">
          <div className="viewer-loading">
            <span className="loading-spinner" />
            <span>加载点云...</span>
          </div>
        </div>
      )}
      
      {/* 错误提示 */}
      {error && (
        <div className="viewer-overlay error">
          <div className="viewer-error">
            <span>⚠️ {error}</span>
          </div>
        </div>
      )}
      
      {/* 信息栏 */}
      {!loading && !error && (
        <div className="viewer-info">
          <span className="point-count">{pointCount.toLocaleString()} 点</span>
          <button className="viewer-btn" onClick={resetView} title="重置视角">
            ⟲
          </button>
        </div>
      )}
    </div>
  );
}

export default PointCloudViewer;
