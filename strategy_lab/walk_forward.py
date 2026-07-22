class WalkForwardSplitter:
    """Create chronological train/test windows without future-data leakage."""

    def split(self, df, train_size, test_size, step=None):
        if train_size <= 0 or test_size <= 0:
            raise ValueError("train_size and test_size must be positive")

        step = step or test_size
        if step <= 0:
            raise ValueError("step must be positive")

        windows = []
        train_start = 0

        while train_start + train_size + test_size <= len(df):
            train_end = train_start + train_size
            test_end = train_end + test_size
            windows.append(
                {
                    "train": df.iloc[train_start:train_end].copy(),
                    "test": df.iloc[train_end:test_end].copy(),
                }
            )
            train_start += step

        return windows
