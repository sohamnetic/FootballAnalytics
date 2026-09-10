import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { uploadMatchVideo } from "../api/getMatchStats";
import { ProductNav } from "../components/ProductNav";

const ACCEPT = ".mp4,.mov,.avi,.mkv,video/mp4,video/quicktime,video/x-msvideo,video/x-matroska";

export function UploadPage() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);

  async function onSubmit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadMatchVideo(file);
      navigate(`/matches/${result.match_id}/setup`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <ProductNav />
      <section className="panel form-panel">
        <div className="kicker">New match</div>
        <h1>Upload match video</h1>
        <p className="hero-copy">MP4 preferred. MOV, AVI, and MKV are also accepted.</p>
        <label className="dropzone">
          <input
            type="file"
            accept={ACCEPT}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <strong>Select footage</strong>
          <span>Drop or browse a match recording</span>
        </label>
        {file ? (
          <div className="file-card">
            {preview ? <video src={preview} controls muted /> : null}
            <div>
              <strong>{file.name}</strong>
              <div className="muted">{(file.size / (1024 * 1024)).toFixed(1)} MB</div>
              <button className="btn ghost" type="button" onClick={() => setFile(null)}>
                Remove / change
              </button>
            </div>
          </div>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
        <div className="hero-actions">
          <Link className="btn ghost" to="/">
            Back
          </Link>
          <button className="btn primary" type="button" disabled={!file || busy} onClick={onSubmit}>
            {busy ? "Uploading…" : "Continue"}
          </button>
        </div>
      </section>
    </div>
  );
}
