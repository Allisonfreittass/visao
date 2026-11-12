import { type ReactNode, useId } from "react";

interface SettingProps {
  title: string;
  description: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  children?: ReactNode;
}

/** One line of the settings: what it is, one sentence on what it does, and a switch. */
export function Setting({ title, description, checked, disabled, onChange, children }: SettingProps) {
  const id = useId();
  return (
    <div className="setting">
      <div className="setting-text">
        <span id={`${id}-t`} className="setting-title">{title}</span>
        <p id={`${id}-d`} className="note">{description}</p>
        {children}
      </div>
      <button
        type="button"
        role="switch"
        className="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-t`}
        aria-describedby={`${id}-d`}
        disabled={disabled}
        onClick={onChange}
      >
        <span aria-hidden="true" />
      </button>
    </div>
  );
}
