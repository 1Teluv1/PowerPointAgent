import { useState } from "react";

const initial = {
  topic: "Q3 사업전략",
  audience: "임원진",
  tone: "professional",
  slide_count: 8,
  notes: ""
};

export default function RequestForm({ onSubmit, loading }) {
  const [form, setForm] = useState(initial);

  function updateField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function buildPayload() {
    return {
      topic: form.topic.trim(),
      audience: form.audience.trim(),
      tone: form.tone,
      slide_count: form.slide_count,
      requirements: form.notes.trim() ? [form.notes.trim()] : []
    };
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(buildPayload());
      }}
    >
      <div className="field">
        <label htmlFor="topic">Topic *</label>
        <input
          id="topic"
          value={form.topic}
          required
          placeholder="AI PPT Agent"
          onChange={(event) => updateField("topic", event.target.value)}
        />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="audience">Audience</label>
          <input
            id="audience"
            value={form.audience}
            placeholder="Developers"
            onChange={(event) => updateField("audience", event.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="slides">Slides *</label>
          <input
            id="slides"
            type="number"
            min={1}
            max={30}
            required
            value={form.slide_count}
            onChange={(event) => updateField("slide_count", Number(event.target.value))}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="tone">Tone</label>
        <select id="tone" value={form.tone} onChange={(event) => updateField("tone", event.target.value)}>
          <option value="modern">Modern</option>
          <option value="professional">Professional</option>
          <option value="educational">Educational</option>
          <option value="premium">Premium</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="notes">Notes</label>
        <textarea
          id="notes"
          value={form.notes}
          placeholder="Visual-first, clean layout, yellow accent"
          onChange={(event) => updateField("notes", event.target.value)}
        />
      </div>

      <button disabled={loading} className="primary" type="submit">
        {loading ? "Running..." : "Run Pipeline"}
      </button>
      <p className="hint">{loading ? "요청을 처리하고 있습니다." : "Ready."}</p>
    </form>
  );
}
