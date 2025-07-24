from .system import System


class Zfs:
    def __init__(self, system_helper: System):
        self._system = system_helper

    def list_pools(self):
        result = self._system._run(["zpool", "list", "-H", "-o", "name"])
        if result.stdout:
            return result.stdout.strip().split('\n')
        return []

    def dataset_exists(self, dataset):
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", dataset], check=False
        )
        return result.returncode == 0

    def get_mountpoint(self, dataset):
        result = self._system._run(
            ["zfs", "get", "-H", "-o", "value", "mountpoint", dataset]
        )
        return result.stdout.strip()

    def create_dataset(self, dataset):
        if not self.dataset_exists(dataset):
            self._system._run(["zfs", "create", dataset])

    def destroy_dataset(self, dataset):
        if self.dataset_exists(dataset):
            self._system._run(["zfs", "destroy", "-r", dataset])

    def set_quota(self, dataset, quota):
        if self.dataset_exists(dataset):
            self._system._run(["zfs", "set", f"quota={quota}", dataset])

    def get_quota(self, dataset):
        if self.dataset_exists(dataset):
            result = self._system._run(
                ["zfs", "get", "-H", "-o", "value", "quota", dataset]
            )
            return result.stdout.strip()
        return None
