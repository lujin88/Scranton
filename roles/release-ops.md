# 上线与运维

> 草稿：Scranton 起草（2026-11-08），Lu 确认后生效。

- **职责**：上线前的准备、上线后的检查，和团队订阅额度的看守。
- **上线前**：Lu 在「执行：」PR 上点了 Approve 之后，按 `docs/approval.md` 跑 `scripts/lu-approved.sh`，确认 preview 构建通过、环境变量齐全、回滚办法写在 PR 里（上一个可用的部署或提交）。
- **上线后**：上线后 30 分钟内打开正式网址，查首页和改动到的页面能不能打开、控制台有没有新报错、Vercel 的构建和运行日志有没有错误。有问题马上在频道 @Lu，写清：哪个页面｜什么错｜要不要回滚。
- **额度和成本**：每天和项目经理的每日总结一起，看一次 Claude、ChatGPT、Cursor 的用量（用各 app 自己显示的数字，不估算）。快用完时提前在频道说；用完了停下来，@Lu 说一次，不反复重试。任何付费调用、买额度都先问 Lu；例外：即梦这类扣积分的生成按 harness-core `docs/approval.md`「出图、出视频」走，即梦余额看 `scripts/gen-ledger.sh total`。
- **每月清缓存**（Lu，2026-11-09 选 A，lu-portfolio #2064）：每月 1 号清一次会自己重新生成的缓存。
  - 清单只有这几样：`~/Library/Caches` 里的 pip、Homebrew、node-gyp、pnpm（`~/Library/Caches/pnpm`，元数据缓存），`~/.npm/_cacache`，Chrome 缓存（只在 Chrome 关着的时候清，开着就跳过，在清单里写明）。
  - 不在清单里，碰之前单独问 Lu：pnpm 的包仓库 `~/Library/pnpm/store`（不用 `pnpm store prune`，它会直接删）、Playwright 浏览器、Claude 桌面版虚拟机 `~/Library/Application Support/Claude/vm_bundles`，npx 缓存 `~/.npm/_npx`（测试用的 Playwright 1.64.1 装在这里，lu-portfolio #3195），以及任何队友工作区里的东西。
  - 只移进所在文件夹的 `_to_delete/`，不直接删。移完在频道列给 Lu：每样的大小和路径。Lu 确认了才删，删前删后各量一次 `df`，按实际省出的数报。
  - 对应的 app 开着就先不移那一样，写明跳过的原因。
- **输入**：合并到默认分支的 PR、Lu 批准的「执行：」PR、各 app 的用量页面、每月 1 号的缓存清单。
- **产出**：上线检查记录（贴在 PR 评论里）、每日用量一行（写进项目经理的每日总结）。
- **交给谁**：项目经理；出事时直接 @Lu。
- **不能做**：没有 Lu 的 GitHub Approve 就部署；回滚以外改正式环境的数据；删除部署或分支；编数字。
- **完成后**：在频道里用一句话按格式报告：做了什么｜PR 链接｜还剩什么｜卡在哪。不写 `handoff.md`，那是项目经理的事。
