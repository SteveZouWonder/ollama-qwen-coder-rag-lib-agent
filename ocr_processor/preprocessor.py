"""
图像预处理器
"""
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class PreprocessConfig:
    """预处理配置"""
    denoise: bool = True           # 去噪
    binarize: bool = True          # 二值化
    deskew: bool = True            # 倾斜校正
    enhance_contrast: bool = True  # 对比度增强
    resize: Optional[Tuple[int, int]] = None  # 调整大小


class ImagePreprocessor:
    """图像预处理器"""
    
    def __init__(self, config: Optional[PreprocessConfig] = None):
        """
        初始化图像预处理器
        
        Args:
            config: 预处理配置
        """
        self.config = config or PreprocessConfig()
    
    def preprocess(self, image_path: Path) -> np.ndarray:
        """
        预处理图像
        
        Args:
            image_path: 图像文件路径
            
        Returns:
            预处理后的图像（numpy 数组）
        """
        import cv2
        
        # 读取图像
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"无法读取图片: {image_path}")
        
        # 转换为灰度图
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 去噪
        if self.config.denoise:
            gray = self._denoise(gray)
        
        # 对比度增强
        if self.config.enhance_contrast:
            gray = self._enhance_contrast(gray)
        
        # 二值化
        if self.config.binarize:
            gray = self._binarize(gray)
        
        # 倾斜校正
        if self.config.deskew:
            gray = self._deskew(gray)
        
        # 调整大小
        if self.config.resize:
            gray = cv2.resize(gray, self.config.resize)
        
        return gray
    
    def _denoise(self, image: np.ndarray) -> np.ndarray:
        """
        去噪
        
        Args:
            image: 输入图像
            
        Returns:
            去噪后的图像
        """
        import cv2
        
        # 使用快速非局部均值去噪
        return cv2.fastNlMeansDenoising(image, h=10)
    
    def _binarize(self, image: np.ndarray) -> np.ndarray:
        """
        二值化
        
        Args:
            image: 输入图像
            
        Returns:
            二值化后的图像
        """
        import cv2
        
        # 使用 Otsu 阈值法自动选择阈值
        _, binary = cv2.threshold(
            image, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        return binary
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        对比度增强
        
        Args:
            image: 输入图像
            
        Returns:
            对比度增强后的图像
        """
        import cv2
        
        # 使用 CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)
    
    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """
        倾斜校正
        
        Args:
            image: 输入图像
            
        Returns:
            校正后的图像
        """
        import cv2
        
        # 计算倾斜角度
        angle = self._get_skew_angle(image)
        
        # 如果倾斜角度很小，不进行校正
        if abs(angle) < 0.5:
            return image
        
        # 旋转图像
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(image, M, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
        
        return rotated
    
    def _get_skew_angle(self, image: np.ndarray) -> float:
        """
        计算图像的倾斜角度
        
        Args:
            image: 输入图像
            
        Returns:
            倾斜角度（度）
        """
        import cv2
        
        # 边缘检测
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        
        # 霍夫变换检测直线
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        
        if lines is None:
            return 0.0
        
        # 计算平均角度
        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = np.degrees(theta) - 90
            angles.append(angle)
        
        # 返回中位数角度（更稳健）
        return np.median(angles)
    
    def resize_image(
        self,
        image: np.ndarray,
        target_size: Tuple[int, int],
        keep_aspect_ratio: bool = True
    ) -> np.ndarray:
        """
        调整图像大小
        
        Args:
            image: 输入图像
            target_size: 目标大小 (width, height)
            keep_aspect_ratio: 是否保持宽高比
            
        Returns:
            调整大小后的图像
        """
        import cv2
        
        if not keep_aspect_ratio:
            return cv2.resize(image, target_size)
        
        # 保持宽高比
        h, w = image.shape[:2]
        target_w, target_h = target_size
        
        # 计算缩放比例
        scale = min(target_w / w, target_h / h)
        
        # 计算新的尺寸
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # 调整大小
        resized = cv2.resize(image, (new_w, new_h))
        
        # 创建目标大小的画布并居中
        canvas = np.zeros((target_h, target_w), dtype=image.dtype)
        y_offset = (target_h - new_h) // 2
        x_offset = (target_w - new_w) // 2
        canvas[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = resized
        
        return canvas
    
    def save_image(self, image: np.ndarray, output_path: Path):
        """
        保存图像
        
        Args:
            image: 图像数组
            output_path: 输出路径
        """
        import cv2
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), image)
