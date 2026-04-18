from __future__ import annotations
import numpy as np


class MuJoCoEnv:
    def __init__(self, urdf_xml: str, render: bool = False) -> None:
        import mujoco
        self.model = mujoco.MjModel.from_xml_string(urdf_xml)
        self.data = mujoco.MjData(self.model)
        self._render = render
        self._renderer = None
        if render:
            self._renderer = mujoco.Renderer(self.model, height=240, width=320)

    def reset(self) -> np.ndarray:
        import mujoco
        mujoco.mj_resetData(self.model, self.data)
        mujoco.mj_forward(self.model, self.data)
        return self._obs()

    def step(self, tau: np.ndarray) -> tuple[np.ndarray, bool]:
        import mujoco
        n = min(len(tau), self.model.nu)
        self.data.ctrl[:n] = tau[:n]
        mujoco.mj_step(self.model, self.data)
        done = bool(self.data.qpos[2] < 0.05) if self.model.nq >= 3 else False
        return self._obs(), done

    def _obs(self) -> np.ndarray:
        return np.concatenate([self.data.qpos.copy(), self.data.qvel.copy()])

    def render_frame(self) -> np.ndarray:
        if self._renderer is None:
            raise RuntimeError("Renderer not enabled. Pass render=True.")
        self._renderer.update_scene(self.data, camera="track")
        return self._renderer.render()

    def rollout_to_video(self, q_target: np.ndarray, fps: int = 30) -> tuple[np.ndarray, list]:
        import mujoco
        frames = []
        traj = []
        self.reset()
        for t in range(q_target.shape[0]):
            n = min(q_target.shape[1], self.model.nq)
            self.data.qpos[:n] = q_target[t, :n]
            mujoco.mj_forward(self.model, self.data)
            traj.append(self.data.qpos.copy())
            if self._renderer is not None:
                frames.append(self.render_frame())
        return np.array(traj), frames

    def save_video(self, frames: list, path: str, fps: int = 30) -> None:
        import subprocess, tempfile, shutil
        tmp = tempfile.mkdtemp()
        try:
            import cv2
            for i, f in enumerate(frames):
                cv2.imwrite(f"{tmp}/{i:05d}.png", f[:, :, ::-1])
            subprocess.run(
                ["ffmpeg", "-y", "-r", str(fps), "-i", f"{tmp}/%05d.png",
                 "-vcodec", "libx264", "-pix_fmt", "yuv420p", path],
                check=True, capture_output=True,
            )
        finally:
            shutil.rmtree(tmp)
