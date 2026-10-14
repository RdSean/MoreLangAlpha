# 学生讲义旁注交互设计与实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 按用户确认的参考图改善学生讲义批注：淡色虚线原句、随原文滚动的右侧精简旁注、双向强调与引用定位。

**Architecture:** 复用 LessonAnnotations 的选段持久化、位置测量及避让，不改变 API 或数据模型。右侧卡片使用已有颜色语义 tokens，引用点击定位原句，悬停及键盘焦点同步强调关联元素；删除由现有保存状态机确认后执行。窄屏沿用点击原文弹出的紧凑编辑框，保持错误草稿与 Chat。

**Tech Stack:** React、CSS、Radix Dialog、Vitest、Playwright。

## 已确认设计

- 正文淡色高亮、细虚线下划线和小圆编号；两套现有浅色主题。
- 旁注与原句对齐，细边框、轻阴影、截断引用及完整批注，底部编辑/删除。
- 悬停或聚焦原句/旁注时关联强调；引用点击滚动定位。多卡片按真实高度避让。
- 窄屏点击原文查看紧凑对话框，不挤压正文；尊重减少动画偏好。
- 不扩展家长端或 PDF 标注，不改后端、数据库或 Docker。

## 实施步骤

- [ ] 添加旁注定位、联动与独立删除确认的回归，先确认旧实现失败。
- [ ] 修改 LessonAnnotations.tsx、lessonAnnotationContext.ts 与 CSS，保留既有定位和数据隔离。
- [ ] 运行聚焦单测、类型检查、样式 token 检查、修改文件 ESLint、构建。
- [ ] 当前 Chromium 和 Chromium 90 检查两套主题与手机/平板/桌面，核对滚动、卡片避让、删除失败及 Chat 草稿，查看截图。
- [ ] 更新中文 CHANGELOG、完成记录、原子提交并检查 LAN 5177。
