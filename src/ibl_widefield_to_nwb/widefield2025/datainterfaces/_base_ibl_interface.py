import time
from abc import abstractmethod

from neuroconv import BaseDataInterface
from one.api import ONE


class BaseIBLDataInterface(BaseDataInterface):
    @classmethod
    @abstractmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        raise NotImplementedError(f"{cls.__name__} must implement get_data_requirements() class method")

    @classmethod
    def download_data(cls, one: ONE, eid: str, download_only: bool = True, **kwargs) -> list:
        """
        Download data using ONE API.

        Uses one.load_dataset() directly. Will raise exception if file missing.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID
        download_only : bool, default=True
            If True, download but don't load into memory

        Returns
        -------
        list
            List of files downloaded
        """
        requirements = cls.get_data_requirements()

        print(f"{cls.__name__} is downloading Widefield data for eid='{eid}' ...")  # (revision {revision})")

        start_time = time.time()
        # NO try-except - let it fail if file missing!
        downloaded_file_paths = []
        for dataset in requirements["exact_files_options"]["standard"]:
            downloaded_file_path = one.load_dataset(
                eid,
                dataset,
                # revision=revision,
                download_only=download_only,
            )
            downloaded_file_paths.append(downloaded_file_path)
        download_time = time.time() - start_time
        print(f"Downloaded Widefield data in {download_time:.2f} seconds.")

        return downloaded_file_paths
