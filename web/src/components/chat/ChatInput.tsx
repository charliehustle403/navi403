import { useState } from "react";

export function ChatInput({
  disabled,
  onSubmit,
}: {
  disabled: boolean;
  onSubmit: (text: string) => void;
}) {
  const [text, setText] = useState("");

  const submit = () => {
    const trimmed = text.trim();
    if (trimmed === "" || disabled) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <form
      className="flex gap-2 border-t border-border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        placeholder={disabled ? "Processing…" : "Ask anything…"}
        autoFocus
        className="readout w-full rounded-md border border-input bg-transparent px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-ring focus:outline-none disabled:opacity-60"
      />
      <button
        type="submit"
        disabled={disabled || text.trim() === ""}
        className="glass rounded-md px-4 text-sm text-primary transition-colors hover:text-foreground disabled:opacity-40"
        aria-label="Send"
      >
        ➤
      </button>
    </form>
  );
}
