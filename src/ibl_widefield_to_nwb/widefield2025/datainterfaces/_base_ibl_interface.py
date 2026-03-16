import time
from abc import abstractmethod

from neuroconv import BaseDataInterface
from one.api import ONE


class BaseIBLDataInterface(BaseDataInterface):
    """Base class for all IBL data interfaces in this project.

    Every concrete interface must implement ``get_data_requirements()`` returning a dict
    with an ``exact_files_options`` key that maps option names to lists of required file
    paths.  A single-format interface uses ``{"standard": [...files...]}``.  Interfaces
    that can be satisfied by more than one set of files (e.g. both NIDQ and DAQ formats)
    list multiple named options — ``check_availability`` succeeds when **any** option's
    files are all present::

        {
            "exact_files_options": {
                "nidq": ["raw_ephys_data/file.nidq.cbin", ...],
                "daq":  ["raw_sync_data/file.cbin", ...],
            }
        }

    Class methods ``check_availability()`` and ``download_data()`` are shared by all
    subclasses and never need to be overridden.
    """

    @classmethod
    @abstractmethod
    def get_data_requirements(cls, **kwargs) -> dict:
        raise NotImplementedError(f"{cls.__name__} must implement get_data_requirements() class method")

    @classmethod
    def check_availability(cls, one: ONE, eid: str, **kwargs) -> dict:
        """
        Check if required data is available for a specific session.

        This method NEVER downloads data - it only checks if files exist
        using one.list_datasets(). It's designed to be fast and read-only,
        suitable for scanning many sessions.

        NO try-except patterns that hide failures. If checking fails,
        let the exception propagate.

        NOTE: Does NOT use revision filtering in check_availability(). Queries for latest
        version of all files regardless of revision tags. This matches the smart fallback
        behavior of load_object() and download methods, which try requested revision first
        but fall back to latest if not found.

        Parameters
        ----------
        one : ONE
            ONE API instance
        eid : str
            Session ID (experiment ID)
        **kwargs : dict
            Interface-specific parameters

        Returns
        -------
        dict
            {
                "available": bool,              # Overall availability
                "missing_required": [str],      # Missing required files
                "found_files": [str],           # Files that exist
                "alternative_used": str,        # Which alternative was found (if applicable)
                "requirements": dict,           # Copy of get_data_requirements()
            }

        Examples
        --------
        >>> result = WheelInterface.check_availability(one, eid)
        >>> if not result["available"]:
        >>>     print(f"Missing: {result['missing_required']}")
        """
        # (QC filtering step reserved for future use — not yet implemented)

        # Check file existence
        requirements = cls.get_data_requirements(**kwargs)

        # Query without revision filtering to get latest version of ALL files
        # This includes both revision-tagged files (spike sorting) and untagged files (behavioral)
        # The unfiltered query returns the superset of what any revision-specific query would return
        available_datasets = one.list_datasets(eid)
        available_files = set(str(d) for d in available_datasets)

        missing_required = []
        found_files = []
        alternative_used = None

        # Check file options - this is now REQUIRED (not optional)
        # Every interface must define exact_files_options dict
        exact_files_options = requirements.get("exact_files_options", {})

        if not exact_files_options:
            raise ValueError(
                f"{cls.__name__}.get_data_requirements() must return 'exact_files_options' dict. "
                f"Even for single-format interfaces, use: {{'standard': ['file1.npy', 'file2.npy']}}"
            )

        # Check each named option - ANY complete option = available
        for option_name, option_files in exact_files_options.items():
            all_files_found = True

            for exact_file in option_files:
                # Handle wildcards
                if "*" in exact_file:
                    import re

                    pattern = re.escape(exact_file).replace(r"\*", ".*")
                    found = any(re.search(pattern, avail) for avail in available_files)
                else:
                    found = any(exact_file in avail for avail in available_files)

                if not found:
                    all_files_found = False
                    break  # This option is incomplete

            # If this option has all files, mark as available
            if all_files_found:
                found_files.extend(option_files)
                alternative_used = option_name  # Report which option was found
                break  # Found one complete option, that's enough

        # If no options were complete, mark the first option as missing for reporting
        if not alternative_used:
            first_option_name = next(iter(exact_files_options.keys()))
            missing_required.extend(exact_files_options[first_option_name])

        result = {
            "available": len(missing_required) == 0,
            "missing_required": missing_required,
            "found_files": found_files,
            "alternative_used": alternative_used,
            "requirements": requirements,
        }
        return result

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

        print(f"{cls.__name__} is downloading Widefield data for eid='{eid}' ...")

        start_time = time.time()
        # No try-except — let it fail if a required file is missing.
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
