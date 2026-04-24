# Windows + GPU + Flash Attention 구성 가이드

## 1. 권장 버전 매트릭스
| 항목 | 권장 |
| --- | --- |
| OS | Windows 11 |
| Python | 3.10.x |
| NVIDIA Driver | CUDA 12.x 대응 최신 안정 버전 |
| CUDA Toolkit | 12.1 또는 12.4 (PyTorch 빌드와 일치) |
| PyTorch | CUDA 빌드 사용 |
| Transformers | 최신 안정 버전 |
| PEFT | 최신 안정 버전 |
| Flash Attention | CUDA/아키텍처 호환 버전 고정 |

## 2. 설치 순서
1. GPU 드라이버 설치
2. Python 가상환경 생성
3. PyTorch CUDA 빌드 설치
4. Transformers/PEFT 설치
5. Flash Attention 설치
6. `python -c "import torch; print(torch.cuda.is_available())"` 확인

## 3. 운영 체크리스트
- 모델 로드 시 GPU 메모리 사용량 모니터링
- Flash Attention 활성화 여부 로그 확인
- 토큰 상한(10,000) 가드 활성화 확인
- Windows 경로/인코딩(UTF-8) 설정 확인
