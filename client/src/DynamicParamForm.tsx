import { ParamFieldSchema } from "./types";
import { formatParamLabel } from "./displayHelpers";

interface DynamicParamFormProps {
  fields: ParamFieldSchema[];
  values: Record<string, any>;
  onChange: (key: string, value: any) => void;
}

export function DynamicParamForm({ fields, values, onChange }: DynamicParamFormProps) {
  return (
    <div className="param-grid">
      {fields.map((field) => {
        const value = values[field.key] ?? field.default;

        if (field.type === "select" && field.choices) {
          return (
            <label className="field compact" key={field.key}>
              <div className="field-label-group">
                <span>{field.label || formatParamLabel(field.key)}</span>
                {field.description && <small title={field.description}>?</small>}
              </div>
              <select 
                value={String(value)} 
                onChange={(e) => onChange(field.key, e.target.value)}
              >
                {field.choices.map((choice) => (
                  <option key={choice.value} value={choice.value}>
                    {choice.label}
                  </option>
                ))}
              </select>
            </label>
          );
        }

        if (field.type === "boolean") {
          return (
            <label className="field compact checkbox-field" key={field.key}>
              <span>{field.label || formatParamLabel(field.key)}</span>
              <input 
                type="checkbox" 
                checked={Boolean(value)} 
                onChange={(e) => onChange(field.key, e.target.checked)}
              />
            </label>
          );
        }

        return (
          <label className="field compact" key={field.key}>
            <div className="field-label-group">
              <span>{field.label || formatParamLabel(field.key)}</span>
              {field.description && <small title={field.description}>?</small>}
            </div>
            <input 
              type={field.type === "number" ? "number" : "text"}
              value={String(value)}
              onChange={(e) => onChange(field.key, field.type === "number" ? Number(e.target.value) : e.target.value)}
              placeholder={String(field.default)}
            />
          </label>
        );
      })}
    </div>
  );
}
