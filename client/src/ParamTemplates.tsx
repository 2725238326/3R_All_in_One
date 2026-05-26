// ═══════════════════════════════════════════════════════════════
// ParamTemplates — 参数模板选择/保存
// ═══════════════════════════════════════════════════════════════
import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "./appConfig";

export type ParamTemplate = {
  id: string;
  name: string;
  model: string;
  source_type: string;
  params: Record<string, any>;
  notes: string;
  created_at: string;
  updated_at: string;
};

interface ParamTemplateSelectorProps {
  model: string;
  currentParams: Record<string, any>;
  currentSourceType: string;
  onApply: (params: Record<string, any>, sourceType: string) => void;
}

export function ParamTemplateSelector({
  model,
  currentParams,
  currentSourceType,
  onApply,
}: ParamTemplateSelectorProps) {
  const [templates, setTemplates] = useState<ParamTemplate[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [showSave, setShowSave] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/templates?model=${encodeURIComponent(model)}`);
      if (res.ok) {
        const data = await res.json();
        setTemplates(data);
      }
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [model]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  async function handleSave() {
    if (!saveName.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: saveName.trim(),
          model,
          params: currentParams,
          source_type: currentSourceType,
        }),
      });
      if (res.ok) {
        setSaveName("");
        setShowSave(false);
        fetchTemplates();
      }
    } catch (e) {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await fetch(`${API_BASE}/api/templates/${id}`, { method: "DELETE" });
      fetchTemplates();
    } catch (e) {
      // ignore
    }
  }

  if (loading && templates.length === 0) {
    return null;
  }

  return (
    <div className="param-templates">
      <div className="param-templates-header">
        <span className="mini-label">参数模板</span>
        <button
          type="button"
          className="ghost-button small"
          onClick={() => setShowSave(!showSave)}
        >
          {showSave ? "取消" : "保存当前"}
        </button>
      </div>

      {showSave && (
        <div className="param-template-save">
          <input
            type="text"
            className="param-template-input"
            placeholder="模板名称"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSave()}
          />
          <button
            type="button"
            className="ghost-button small primary"
            onClick={handleSave}
            disabled={saving || !saveName.trim()}
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      )}

      {templates.length > 0 && (
        <div className="param-template-list">
          {templates.map((tpl) => (
            <div key={tpl.id} className="param-template-item">
              <button
                type="button"
                className="param-template-apply"
                onClick={() => onApply(tpl.params, tpl.source_type)}
                title={`应用模板：${tpl.name}\n${tpl.updated_at}`}
              >
                <strong>{tpl.name}</strong>
                <span>{Object.keys(tpl.params).length} 个参数</span>
              </button>
              <button
                type="button"
                className="param-template-delete"
                onClick={() => handleDelete(tpl.id)}
                title="删除模板"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
