"""Optional Keras LSTM adapter. TensorFlow is imported only when LSTM is requested."""
from __future__ import annotations

from pathlib import Path
import os
import tempfile
import threading
import numpy as np
from preprocessing import DataPreparationError

_TF_LOCK = threading.Lock()


def tensorflow():
    os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
    try:
        import tensorflow as tf
    except ImportError as exc:
        raise DataPreparationError('LSTM 需要本機 TensorFlow。請先執行 SETUP_LSTM.bat，再重新啟動本機程式。') from exc
    try:
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.threading.set_intra_op_parallelism_threads(2)
    except RuntimeError:
        pass  # Already initialized in this process.
    return tf


class LSTMRegressor:
    def __init__(self, lookback, channels, units=32, epochs=30, batch_size=32, seed=42):
        self.lookback, self.channels = lookback, channels
        self.units, self.epochs, self.batch_size, self.seed = units, epochs, batch_size, seed
        self._model = None

    def _sequence(self, X):
        flat = X.toarray() if hasattr(X, 'toarray') else np.asarray(X)
        if flat.shape[1] != self.lookback * self.channels:
            raise DataPreparationError('LSTM 輸入形狀與歷史視窗不符。')
        return flat.astype('float32').reshape(-1, self.channels, self.lookback).transpose(0, 2, 1)

    def fit(self, X, y, validation=None):
        with _TF_LOCK:
            tf = tensorflow()
            tf.keras.backend.clear_session()
            tf.keras.utils.set_random_seed(self.seed)
            sequence = self._sequence(X)
            y = np.asarray(y, dtype='float32')
            self.y_mean = float(np.mean(y))
            self.y_scale = float(np.std(y)) or 1.
            scaled = (y - self.y_mean) / self.y_scale
            model = tf.keras.Sequential([
                tf.keras.layers.Input(shape=(self.lookback, self.channels)),
                tf.keras.layers.LSTM(self.units),
                tf.keras.layers.Dense(16, activation='relu'),
                tf.keras.layers.Dense(1),
            ])
            model.compile(optimizer='adam', loss='mse')
            options = tf.data.Options()
            options.threading.private_threadpool_size = 1
            options.threading.max_intra_op_parallelism = 1
            def dataset(a, b):
                return tf.data.Dataset.from_tensor_slices((a, b)).batch(self.batch_size).with_options(options)
            kwargs = {}
            if validation is not None:
                vx, vy = validation
                kwargs['validation_data'] = dataset(self._sequence(vx), (np.asarray(vy) - self.y_mean) / self.y_scale)
                kwargs['callbacks'] = [tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)]
            history = model.fit(dataset(sequence, scaled), epochs=self.epochs, verbose=0, shuffle=False, **kwargs)
            self.best_epoch = int(np.argmin(history.history['val_loss']) + 1) if validation is not None else self.epochs
            self.training_history = {k: [float(x) for x in v] for k, v in history.history.items()}
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'model.keras'
                model.save(path)
                self.keras_bytes = path.read_bytes()
            self._model = model
        return self

    def predict(self, X):
        if self._model is None:
            tf = tensorflow()
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'model.keras'
                path.write_bytes(self.keras_bytes)
                self._model = tf.keras.models.load_model(path, compile=False, safe_mode=True)
        sequence = self._sequence(X)
        values = np.concatenate([np.asarray(self._model(sequence[i:i + self.batch_size], training=False)).ravel()
                                 for i in range(0, len(sequence), self.batch_size)])
        return values * self.y_scale + self.y_mean

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k != '_model'}

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._model = None
