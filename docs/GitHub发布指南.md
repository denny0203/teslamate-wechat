# GitHub 发布与后续同步

本地开源目录名为 `teslamate-wechat`。发布时该目录本身应成为仓库根目录。不要在它的父级个人项目目录执行 `git add` 或初始化整个工作区。

2026-10-04：已创建空公开仓库 [denny0203/teslamate-wechat](https://github.com/denny0203/teslamate-wechat)。尚未初始化本地Git、提交或上传代码；待维护者确认本地待上传包后再发布。

## 发布时需要提供什么

- GitHub用户名或目标组织名。
- 仓库名，建议 `teslamate-wechat`；可直接提供已创建的空仓库URL。
- 需要本项目公开发布的明确指令；本项目默认准备为公开仓库。
- 本机是否已有 GitHub 登录或 SSH 授权。若没有，通过自己的浏览器完成登录。

不需要提供服务器密码、微信密码、Supabase管理密钥、GitHub密码或Token到聊天。登录可通过 `gh auth login --web` 或 GitHub Desktop 的浏览器流程完成。[GitHub 官方认证说明](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github)

## 首次发布前

在开源目录中执行：

```bash
node --test tests/*.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/audit_public.py
bash -n ops/bootstrap.sh ops/install_sync.sh
```

有 Docker 时，追加配置检查，避免展开输出密钥：

```bash
docker compose --env-file ops/.env.example -f ops/compose.yaml config --quiet
```

本地运行时若已将 `project.config.json` 改成自己的AppID，公开提交前还原为 `touristappid`，避免提交个人项目标识。

扫描工具只检查常见敏感特征和个人标识，是启发式检查，不能证明所有秘密均不存在。人工复核代码、配置模板、文档、图片和将要提交的差异；本仓库不收录真实数据。当前无需将个人服务器密钥轮换作为开源的前置条件；若后续发现凭据确实泄露，应立即在对应平台撤销／更换。

MIT许可证已准备；确认接受该许可后再发布。首次公开版本应描述为“个人v1.0整理的开源版本，尚未在全新云环境完整复现”，不要把原私有部署的测试当成开源副本验证。

## 推荐：创建空仓库再推送

1. 登录GitHub，创建新仓库，填写名称与描述，选择Public。
2. 不勾选生成README、`.gitignore`或LICENSE，以免与本地文件形成不同初始历史。
3. 获取仓库的HTTPS或SSH URL。
4. 在开源目录完成本地提交与推送。

参考[GitHub 创建仓库说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)。下面命令仅为待执行步骤；没有自动运行。

```bash
git init -b main
```

先确认 `git config user.name` 与 `git config user.email` 已按自己的意愿配置。可使用GitHub账号设置中的noreply邮箱，避免公开个人邮箱；不要由脚本猜测作者身份。

使用明确目录暂存：

```bash
git add README.md LICENSE THIRD_PARTY.md .gitignore .github backend miniprogram ops tools tests docs
git status --short
git diff --cached --stat
python3 tools/audit_public.py
git diff --cached
```

`git diff --cached` 仅在自己的安全终端查看；若发现意外凭据，先取消暂存、清理并重新扫描，不把输出复制到公共讨论或日志。

```bash
git commit -m "Release v1.0 open-source edition"
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```

HTTPS认证推荐先执行浏览器授权：

```bash
gh auth login --web
gh auth setup-git
```

推送后查看GitHub Actions的Checks结果，核对README、许可证、部署教程和所有文件，确认没有私有配置。Actions通过后可创建 `v1.0.0` 标签与Release。标签对应开源发行版，不代表原微信后台版本已正式发布。

## 后续如何同步

两套代码分别维护：原个人项目用于自己的服务，开源仓库用于通用发行。不要将整个个人项目覆盖到公开仓库。

每次只选择需要公开的功能修改，手动移植到开源目录，保留开源配置入口和原创素材，运行测试、扫描，再查看差异、提交和推送：

```bash
git diff
node --test tests/*.test.js
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/audit_public.py
git add README.md THIRD_PARTY.md .github backend miniprogram ops tools tests docs
git diff --cached --stat
git commit -m "Describe the public change"
git push
```

如果另一个设备也在维护，编辑前先检查工作区并 `git pull --ff-only`。有本地改动或分支分歧时先处理，不用force-push覆盖他人的提交。

公开后不要提交运行生成的 `config.js`、`supabase.json`、`amap.json`、`.env`、回填manifest、用户截图和备份。`.gitignore`只保护未跟踪文件，已经提交过的秘密仍存在于历史；确有泄露时先撤销凭据，再按GitHub官方流程清理历史。
