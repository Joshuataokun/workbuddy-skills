# TTMS 企业商旅酒店 (ttms-hotel)

**触发词**：企业出差、商旅酒店、差标酒店、成本中心、审批单、员工差标。

**工具链路**：`hotelSearch` → `hotelDetail` → `hotelSubmitOrder` → `hotelConfirmOrder`；取消：`hotelCancelOrder`

参数详情：`tuniu help ttms-hotel <tool>` 或 `tuniu schema ttms-hotel -o json`

## 与普通 hotel 分流（调用前必读）

用户明确表达企业出差、员工差标、成本中心或审批单等商旅语义时，进入商旅路径，按序执行：

1. **有 `TUNIU_TTMS_API_KEY`** → 调用本服务（`ttms-hotel`）查商旅酒店。
2. **无商旅 Key** → **禁止**调用本服务；提示用户：获取并配置商旅 Key，或改查频道酒店 `hotel`，由用户选择。
3. **商旅查询失败**（认证失败、无权限、业务错误等）→ 向用户说明原因；**仅当用户明确同意**改查频道酒店后，再走 `hotel`。未经同意不得自动降级。

## 认证与环境

- 默认生产地址：`https://openapi.tuniu.cn/mcp/ttms/hotel`
- 必须使用独立的 `TUNIU_TTMS_API_KEY`（`ttms-member` 创建的 `sk-` 开头员工 CLI API Key）
- **不支持**普通服务 OAuth 或 `TUNIU_API_KEY` 替代
- 只有明确进行 PRE 调试时才使用 `-p development`

```bash
export TUNIU_TTMS_API_KEY=sk-your_ttms_api_key
```

## 身份与下单红线（非常重要）

1. **`companyId`、`employeeId`、权限 Scope** 必须来自认证上下文，**禁止**作为 Tool 参数传入。
2. **`preBookParam`** 须来自本轮 `hotelDetail` 返回，短时有效；超时须重新查详情，禁止编造或复用旧值。
3. **提交与确认分离**：`hotelSubmitOrder` 与 `hotelConfirmOrder` 是两个独立步骤；**只有用户明确确认后**才能调用 `hotelConfirmOrder`。
4. **用户信息必须真实**：入住人/联系人信息须为用户提供的真实值，禁止虚构。

## 调用模板

```bash
# 搜索（checkIn、checkOut 可选，但必须同时传入）
tuniu call ttms-hotel hotelSearch --source <source> -a '{"cityName":"南京","checkIn":"2026-10-10","checkOut":"2026-10-11"}'

# 带关键词
tuniu call ttms-hotel hotelSearch --source <source> -a '{"cityName":"南京","checkIn":"2026-10-10","checkOut":"2026-10-11","keyword":"新街口"}'

# 详情（调用前用 schema/help 确认必填参数）
tuniu call ttms-hotel hotelDetail --source <source> -a '{"hotelId":"xxx","checkIn":"2026-10-10","checkOut":"2026-10-11"}'

# 提交订单（须最新 preBookParam；参数以 schema 为准）
tuniu call ttms-hotel hotelSubmitOrder --source <source> -a '{"preBookParam":"xxx","roomGuests":[...]}'

# 确认订单（须用户明确确认后）
tuniu call ttms-hotel hotelConfirmOrder --source <source> -a '{"orderId":"xxx"}'

# 取消订单
tuniu call ttms-hotel hotelCancelOrder --source <source> -a '{"orderId":"xxx"}'
```

## 场景示例

**用户**：9月1号去南京出差，按我的公司差标查新街口附近酒店

**判断**：

1. 含出差/差标 → 商旅语义成立，进入本路径（不是普通 `hotel`）
2. 已配置 `TUNIU_TTMS_API_KEY` → 调用 `ttms-hotel`
3. 未配置 → 提示获取商旅 Key，或询问是否改查频道酒店 `hotel`
4. 商旅调用失败且用户同意 → 改走 `hotel`

```bash
# 有 TUNIU_TTMS_API_KEY 时
tuniu call ttms-hotel hotelSearch --source <source> -a '{"cityName":"南京","checkIn":"2026-10-10","checkOut":"2026-10-11","keyword":"新街口"}'

# 用户同意降级后
tuniu call hotel tuniuHotelSearch --source <source> -a '{"cityName":"南京","checkIn":"2026-10-10","checkOut":"2026-10-11"}'
```
