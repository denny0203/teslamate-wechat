# 第三方与素材声明

| 项目 | 使用方式 | 许可／说明 |
|---|---|---|
| [wandergis/coordtransform](https://github.com/wandergis/coordtransform) | `backend/drive_details.py` 的 WGS84 → GCJ02 转换公式 | MIT，原声明位于 `backend/licenses/coordtransform-MIT.txt`，需随分发保留 |
| [TeslaMate](https://github.com/teslamate-org/teslamate) | 外部 Docker 服务及数据库查询；能耗公式参考其行程面板 | 独立上游项目，遵守上游许可；本仓库不包含 TeslaMate 源码或镜像 |
| PostgreSQL、Eclipse Mosquitto、Grafana | Compose 中的外部镜像 | 各自上游许可；不随仓库再分发镜像 |
| 微信、腾讯地图、Supabase、阿里云、高德 | 部署时的外部服务 | 由部署者自行开通并遵守对应服务条款 |
| Pillow | 可选的素材重建工具 | 不属于服务运行依赖；由部署者自行安装 |

`miniprogram/assets/` 的全部 PNG 均由 `tools/generate_assets.py` 通过几何图形生成，作为本项目原创素材按 MIT 许可分发。原个人版车辆图片、预览码、地图截图、真实轨迹和历史发布包均未复制。

车辆示意图不代表实际车型。保留产品名称不意味着品牌方授权或背书。
