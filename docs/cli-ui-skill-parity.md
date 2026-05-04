# CLI → UI Skill Parity (FlowKit)

Date: 2026-05-02

Legend:
- `FULL`: Có UI + API + flow chạy trong app
- `PARTIAL`: Có trong app nhưng chưa đạt toàn bộ behavior của skill CLI

| Skill | Status | Evidence |
|---|---|---|
| `fk:add-material` | FULL | `desktop/src/pages/SettingsPage.tsx`, `agent/api/materials.py` |
| `fk:change-model` | FULL | `desktop/src/pages/SettingsPage.tsx`, `agent/api/models.py` |
| `fk:create-project` | FULL | `desktop/src/components/projects/AISetupModal.tsx`, `desktop/src/components/projects/CreateProjectModal.tsx`, `agent/api/projects.py` |
| `fk:switch-project` | FULL | `agent/api/active_project.py`, `desktop/src/pages/DashboardPage.tsx`, `desktop/src/pages/ProjectDetailPage.tsx` |
| `fk:gen-refs` | FULL | `desktop/src/pages/ProjectDetailPage.tsx`, `/api/requests/batch` |
| `fk:gen-images` | FULL | `desktop/src/pages/VideoDetailPage.tsx`, `/api/requests/batch` |
| `fk:gen-videos` | FULL | `desktop/src/pages/VideoDetailPage.tsx`, `/api/requests/batch` |
| `fk:gen-chain-videos` | FULL | `desktop/src/components/pipeline/ChainVideosModal.tsx` |
| `fk:insert-scene` | FULL | `desktop/src/components/projects/AddSceneModal.tsx`, `agent/api/scenes.py` (INSERT + auto-shift) |
| `fk:review-video` | FULL | `desktop/src/components/pipeline/ReviewVideoModal.tsx`, `agent/api/reviews.py` |
| `fk:review-board` | FULL | `desktop/src/components/pipeline/ReviewBoardModal.tsx` |
| `fk:gen-text-overlays` | FULL | `desktop/src/components/pipeline/TextOverlaysModal.tsx`, `agent/api/workflows.py` |
| `fk:gen-tts-template` | FULL | `desktop/src/components/pipeline/TTSSetupModal.tsx`, `agent/api/tts.py` |
| `fk:import-voice` | FULL | `desktop/src/components/pipeline/TTSSetupModal.tsx`, `agent/api/tts.py` |
| `fk:gen-tts` | FULL | `desktop/src/components/pipeline/TTSSetupModal.tsx`, `POST /api/videos/{id}/narrate` |
| `fk:gen-narrator` | FULL | `desktop/src/components/pipeline/GenNarratorModal.tsx` |
| `fk:concat` | FULL | `desktop/src/components/pipeline/ExportModal.tsx`, `agent/api/videos.py` |
| `fk:concat-fit-narrator` | FULL | `desktop/src/components/pipeline/ExportModal.tsx` (`fit_narrator`) |
| `fk:gen-music` | FULL | `desktop/src/components/pipeline/MusicModal.tsx`, `agent/api/music.py` |
| `fk:brand-logo` | FULL | `desktop/src/components/pipeline/BrandLogoModal.tsx`, `agent/api/workflows.py` |
| `fk:thumbnail` | FULL | `desktop/src/components/pipeline/ThumbnailModal.tsx`, `agent/api/projects.py` |
| `fk:thumbnail-guide` | FULL | `desktop/src/components/pipeline/GuideModal.tsx` |
| `fk:camera-guide` | FULL | `desktop/src/components/pipeline/GuideModal.tsx` |
| `fk:youtube-seo` | FULL | `desktop/src/components/pipeline/YouTubeSEOModal.tsx`, `agent/api/youtube.py` |
| `fk:youtube-upload` | FULL | `desktop/src/components/pipeline/YouTubeUploadModal.tsx`, `agent/api/youtube.py` |
| `fk:refresh-urls` | FULL | `desktop/src/components/pipeline/RefreshURLsModal.tsx`, `agent/api/flow.py` |
| `fk:fix-uuids` | FULL | `desktop/src/components/pipeline/FixUUIDsModal.tsx` |
| `fk:upload-image` | FULL | `desktop/src/components/pipeline/UploadImageModal.tsx`, `agent/api/flow.py` |
| `fk:creative-mix` | FULL | `desktop/src/components/pipeline/CreativeMixModal.tsx` |
| `fk:pipeline` | FULL | `desktop/src/components/pipeline/PipelineOrchestratorModal.tsx`, `agent/api/workflows.py` (`smart-continue`) |
| `fk:status` | FULL | `desktop/src/components/pipeline/PipelineOrchestratorModal.tsx`, `agent/api/workflows.py` (`/status`) |
| `fk:research` | FULL | `desktop/src/components/projects/AISetupModal.tsx`, `agent/api/workflows.py` (`/research`) |
| `fk:dashboard` | FULL | `agent/api/workflows.py` (`/statusline`), `desktop/src/components/logs/StatusDashboard.tsx`, `desktop/src/components/pipeline/PipelineOrchestratorModal.tsx` |
| `fk:monitor` | FULL | `agent/api/workflows.py` (`/monitor/start`, `/monitor/stop`, `/monitor/state` + Telegram + auto-download), `desktop/src/components/pipeline/PipelineOrchestratorModal.tsx` |
