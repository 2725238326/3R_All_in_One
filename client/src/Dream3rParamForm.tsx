export type Dream3rCacheFileOption = {
  value: string;
  label: string;
};

export type Dream3rCacheSourceOption = {
  value: string;
  label: string;
  detail: string;
  group: "platform" | "history" | "upload";
  domain?: "kitti" | "eth3d";
  jobId?: string;
  createdAt?: string;
  notes?: string;
  cacheFiles?: Dream3rCacheFileOption[];
};

type Props = {
  values: Record<string, any>;
  cacheSources: Dream3rCacheSourceOption[];
  onChange: (patch: Record<string, any>) => void;
};

const SOURCE_GROUP_LABELS: Record<Dream3rCacheSourceOption["group"], string> = {
  platform: "平台内置数据",
  history: "历史任务数据",
  upload: "本机文件",
};

export function Dream3rParamForm({ values, cacheSources, onChange }: Props) {
  const mode = String(values.demo_mode ?? "synthetic");
  const domain = String(values.domain ?? "kitti");
  const cacheSource = String(values.cache_source ?? "server:kitti");
  const selectedSource = cacheSources.find((item) => item.value === cacheSource) ?? cacheSources[0];
  const cacheFiles = selectedSource?.cacheFiles ?? [];
  const cacheFile = String(values.cache_file ?? "");
  const selectedFile = cacheFiles.find((item) => item.value === cacheFile) ?? (cacheFiles.length === 1 ? cacheFiles[0] : undefined);
  const effectiveDomain = selectedSource?.domain ?? domain;
  const expertOrder = effectiveDomain === "eth3d"
    ? ["Fast3R", "MASt3R", "Spann3R", "VGGT-Omega"]
    : ["Fast3R", "MASt3R", "Spann3R"];
  const sourceGroups = (["platform", "history", "upload"] as const)
    .map((group) => ({ group, sources: cacheSources.filter((source) => source.group === group) }))
    .filter((entry) => entry.sources.length > 0);

  function setCacheSource(value: string) {
    const source = cacheSources.find((item) => item.value === value);
    onChange({
      cache_source: value,
      cache_file: source?.cacheFiles?.length === 1 ? source.cacheFiles[0].value : "",
      domain: source?.domain ?? domain,
    });
  }

  return (
    <div className="dream3r-config">
      <div className="dream3r-mode-switch" role="group" aria-label="Dream3R 运行模式">
        <button className={mode === "synthetic" ? "active" : ""} type="button" onClick={() => onChange({ demo_mode: "synthetic" })}>
          <strong>快速演示</strong>
          <span>自动生成标准候选输入</span>
        </button>
        <button className={mode === "cache" ? "active" : ""} type="button" onClick={() => onChange({ demo_mode: "cache" })}>
          <strong>真实多专家融合</strong>
          <span>选择同场景的专家候选缓存包</span>
        </button>
      </div>

      {mode === "synthetic" ? (
        <>
          <div className="dream3r-mode-note">
            适合软件演示和链路检查。无需上传图片或 cache，程序会自动构造候选几何。
          </div>
          <div className="param-grid">
            <SelectField label="模型分支" value={domain} onChange={(value) => onChange({ domain: value })} options={[
              ["kitti", "KITTI 分支"], ["eth3d", "ETH3D 分支"],
            ]} />
            <DeviceField value={String(values.device ?? "auto")} onChange={(value) => onChange({ device: value })} />
            <NumberField label="随机种子" value={Number(values.seed ?? 7)} min={0} onChange={(value) => onChange({ seed: value })} />
            <NumberField label="批次数" value={Number(values.batch ?? 2)} min={1} max={16} onChange={(value) => onChange({ batch: value })} />
            <NumberField label="候选视图数" value={Number(values.views ?? 2)} min={1} max={16} onChange={(value) => onChange({ views: value })} />
            <NumberField label="每视图 Patch 数" value={Number(values.patches ?? 8)} min={1} onChange={(value) => onChange({ patches: value })} />
          </div>
          <div className="dream3r-run-summary">
            <strong>本次运行</strong>
            <span>自动生成输入 · {domain.toUpperCase()} 分支 · {String(values.device ?? "auto")} 设备</span>
          </div>
        </>
      ) : (
        <>
          <div className="dream3r-mode-note">
            缓存包中的每条数据都包含同一场景的多模型结果。不同任务彼此独立，平台不会跨任务拼接内容。
          </div>
          <div className="dream3r-cache-fields">
            <label className="field compact dream3r-cache-source">
              <span>缓存数据来源</span>
              <select value={cacheSource} onChange={(event) => setCacheSource(event.target.value)}>
                {sourceGroups.map(({ group, sources }) => (
                  <optgroup key={group} label={SOURCE_GROUP_LABELS[group]}>
                    {sources.map((source) => <option key={source.value} value={source.value}>{source.label}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>

            {selectedSource && (
              <div className="dream3r-source-inspector">
                <div className="dream3r-source-title">
                  <strong>{selectedSource.label}</strong>
                  <span>{effectiveDomain.toUpperCase()}</span>
                </div>
                <p>{selectedSource.detail}</p>
                <div><b>专家结果</b><span>{expertOrder.join(" + ")}</span></div>
                {selectedSource.jobId && <div><b>来源任务</b><span>{selectedSource.jobId}</span></div>}
                {selectedSource.createdAt && <div><b>创建时间</b><span>{selectedSource.createdAt}</span></div>}
                {selectedSource.notes && <div><b>任务备注</b><span>{selectedSource.notes}</span></div>}
              </div>
            )}

            {cacheFiles.length > 1 && (
              <label className="field compact">
                <span>本次使用的缓存包文件</span>
                <select value={cacheFile} onChange={(event) => onChange({ cache_file: event.target.value })}>
                  <option value="">请选择一个文件</option>
                  {cacheFiles.map((file) => <option key={file.value} value={file.value}>{file.label}</option>)}
                </select>
                <small className="field-help">每个文件都应当已经包含完整的同场景多专家结果；系统不会把不同任务临时拼成一个场景。</small>
              </label>
            )}

            {cacheFiles.length === 1 && (
              <div className="dream3r-fixed-file"><b>缓存包</b><span>{cacheFiles[0].label}</span></div>
            )}

            <div className="param-grid">
              <SelectField label="缓存所属数据域" value={effectiveDomain} onChange={(value) => onChange({ domain: value })} options={[
                ["kitti", "KITTI"], ["eth3d", "ETH3D"],
              ]} disabled={Boolean(selectedSource?.domain)} />
              <NumberField
                label="处理条目数"
                value={Number(values.max_entries ?? 1)}
                min={1}
                max={50}
                onChange={(value) => onChange({ max_entries: value })}
              />
              <DeviceField value={String(values.device ?? "auto")} onChange={(value) => onChange({ device: value })} />
            </div>
          </div>
          <div className="dream3r-run-summary">
            <strong>本次运行</strong>
            <span>{selectedSource?.label ?? "未选择来源"} · {expertOrder.length} 个专家 · {selectedFile?.label ?? (cacheFiles.length > 1 ? "尚未选择缓存包" : "固定缓存包")} · 取前 {Number(values.max_entries ?? 1)} 条</span>
          </div>
        </>
      )}
    </div>
  );
}

function DeviceField(props: { value: string; onChange: (value: string) => void }) {
  return <SelectField label="运行设备" value={props.value} onChange={props.onChange} options={[
    ["auto", "自动选择"], ["cuda", "GPU (CUDA)"], ["cpu", "CPU"],
  ]} />;
}

function SelectField(props: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="field compact">
      <span>{props.label}</span>
      <select value={props.value} disabled={props.disabled} onChange={(event) => props.onChange(event.target.value)}>
        {props.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
    </label>
  );
}

function NumberField(props: {
  label: string;
  value: number;
  min: number;
  max?: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="field compact">
      <span>{props.label}</span>
      <input type="number" value={props.value} min={props.min} max={props.max} onChange={(event) => props.onChange(Number(event.target.value))} />
    </label>
  );
}
