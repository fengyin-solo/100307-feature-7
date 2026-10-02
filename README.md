# 通信基站运维管理平台

面向通信基站站点入网、动力环境监控、天馈巡检、发电保障与退网拆站的一体化基站运维管理后台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 基站台账 | `site` | 基站 | 基站编号、基站名称、基站类型 |
| 铁塔管理 | `tower` | 铁塔 | 铁塔编号、铁塔类型、设计高度 |
| 动力配套 | `power` | 电源设备 | 设备编号、设备类型、额定功率 |
| 蓄电池组 | `battery` | 蓄电池组 | 电池组编号、电池类型、额定容量 |
| 发电机组 | `genset` | 发电机组 | 机组编号、机组型号、额定功率 |
| 开关电源 | `rectifier` | 开关电源 | 电源编号、额定功率、所属站点 |
| 空调管理 | `ac` | 空调 | 空调编号、空调类型、制冷量 |
| 天馈系统 | `antenna` | 天馈设备 | 天馈编号、天线类型、工作频段 |
| 传输设备 | `transmission` | 传输设备 | 设备编号、传输类型、带宽容量 |
| 馈线巡检 | `feeder` | 馈线 | 馈线编号、所属站点、馈线长度 |
| 防雷接地 | `lightningprot` | 防雷装置 | 装置编号、所属站点、接地电阻、下次复测日 |
| 消防设施 | `firealarm` | 消防设施 | 设施编号、设施类型、所属站点 |
| 门禁管理 | `dooraccess` | 门禁记录 | 门禁编号、所属站点、开门方式 |
| 巡检作业 | `patrol` | 巡检任务 | 任务编号、巡检站点、巡检人员 |
| 油料管理 | `fuel` | 油料记录 | 记录编号、所属站点、油料类型 |
| 场租合同 | `rental` | 场租合同 | 合同编号、站点名称、出租方 |
| 电费管理 | `electricbill` | 电费记录 | 记录编号、所属站点、电表读数 |
| 拆站管理 | `demolition` | 拆站任务 | 任务编号、拆除站点、拆除原因 |
| 应急通信 | `emergency` | 应急保障 | 保障编号、保障类型、保障地点 |
| 节能改造 | `energyeff` | 节能项目 | 项目编号、所属站点、改造内容 |

## 防雷装置复测队列

防雷接地页按三个页签组织：复测队列、装置台账、周期设置。

- **复测队列**（`GET /api/lightningprot/retest-queue`）：按站点分组列出在队装置与下次复测日，
  按「电阻超标 → 已超期 → 临近复测（默认 30 天窗口）」排序，站点顺序同样按最紧迫的一台排；
  电阻超标的单独呈现，并标注是历次测试中的第几次测超、测试日期/读数/人员。
- **登记复测**（`POST /api/lightningprot/{id}/retest`）：每次登记都追加一条接地电阻测试记录。
  读数 ≤10Ω 判合格，下次复测日按「测试日期 + 当前复测周期」重排，装置本轮退出队列；仍超标则留队整改。
- **浪涌模块更换**（`POST /api/lightningprot/{id}/spd-replacement`）：更换浪涌保护模块时一并登记
  更换后的测试，测试人员、测试日期随更换记录同步更新。
- **周期设置**（`GET/PUT /api/lightningprot/retest-settings`）：调整复测周期后，全部已有装置的
  下次复测日按新周期、从各自最近一次测试日期逐台重排。
- 装置台账与复测队列共用同一套派生口径（状态只由最近一次测试推导），两处结论保持一致；
  单台装置的历次测试可通过 `GET /api/lightningprot/{id}` 查看。

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
