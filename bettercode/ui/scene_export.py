from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgGenerator
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView


def export_scene_image(
    *,
    view: QGraphicsView,
    scene: QGraphicsScene,
    output_path: str | Path,
    padding: float = 24.0,
) -> Path:
    if not scene.items():
        raise ValueError("Scene is empty")

    path = Path(output_path)
    scene_rect = scene.sceneRect()
    if scene_rect.isNull() or scene_rect.isEmpty():
        scene_rect = scene.itemsBoundingRect()
    if scene_rect.isNull() or scene_rect.isEmpty():
        raise ValueError("Scene bounds are empty")

    source_rect = scene_rect.adjusted(-padding, -padding, padding, padding)
    image_width = max(1, int(math.ceil(source_rect.width())))
    image_height = max(1, int(math.ceil(source_rect.height())))
    background_color = view.backgroundBrush().color()
    if not background_color.isValid():
        background_color = QColor("#0e1422")

    if path.suffix.lower() == ".svg":
        generator = QSvgGenerator()
        generator.setFileName(str(path))
        generator.setSize(generator_size := path_size(image_width, image_height))
        generator.setViewBox(QRectF(0, 0, image_width, image_height).toRect())
        generator.setTitle(path.stem)
        painter = QPainter(generator)
        painter.fillRect(QRectF(0, 0, image_width, image_height), background_color)
        painter.setRenderHint(QPainter.Antialiasing)
        scene.render(painter, target=QRectF(0, 0, image_width, image_height), source=source_rect)
        painter.end()
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError(f"Could not save image to {path}")
        return path

    image = QImage(image_width, image_height, QImage.Format_ARGB32_Premultiplied)
    image.fill(background_color)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scene.render(painter, target=QRectF(0, 0, image_width, image_height), source=source_rect)
    painter.end()

    if not image.save(str(path)):
        raise OSError(f"Could not save image to {path}")
    return path


def path_size(width: int, height: int):
    from PySide6.QtCore import QSize

    return QSize(width, height)
