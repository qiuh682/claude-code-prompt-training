# Day 2: Task Decomposition
# 第二天：任务分解

**Duration / 时长**: 1-1.5 hours / 1-1.5小时

---

## Learning Objectives / 学习目标
- Break complex tasks into manageable steps / 将复杂任务分解为可管理的步骤
- Understand task dependencies / 理解任务依赖关系
- Create effective task sequences / 创建有效的任务序列

---

## Core Concepts / 核心概念

### 1. Why Decompose? / 为什么要分解？

```
❌ One Big Prompt / 一个大提示词:
"Build a user authentication system"
→ Overwhelming, easy to miss details, hard to verify
→ 难以处理，容易遗漏细节，难以验证

✅ Decomposed Prompts / 分解的提示词:
Step 1: Create user schema
Step 2: Implement password hashing
Step 3: Create registration endpoint
...
→ Manageable, testable, verifiable
→ 可管理，可测试，可验证
```

### 2. When to Decompose vs. Single Prompt / 何时分解 vs 单个提示词

| Single Prompt / 单个提示词 | Decomposed / 分解 |
|---------------------------|-------------------|
| Simple function / 简单函数 | Multi-file changes / 多文件更改 |
| Bug fix / Bug修复 | New features / 新功能 |
| Code review / 代码审查 | System architecture / 系统架构 |
| Explanation / 解释说明 | Refactoring / 重构 |

### 3. The Decomposition Process / 分解过程

```
Complex Task
    │
    ▼
┌─────────────┐
│ Decompose   │ → What are the pieces?
├─────────────┤
│ Dependencies│ → What needs what?
├─────────────┤
│ Parallelize │ → What can run together?
├─────────────┤
│ Sequence    │ → What's the order?
├─────────────┤
│ Chain       │ → How do prompts connect?
└─────────────┘
    │
    ▼
Series of focused, testable prompts
一系列聚焦的、可测试的提示词
```

---

## Exercises with Solutions / 练习与答案

### Exercise 2.1: Decompose a Feature / 分解一个功能

**Task / 任务:** Add a shopping cart feature to an e-commerce site
为电商网站添加购物车功能

---

#### Decomposed Steps / 分解步骤:

```
Step 1: Design Cart Data Schema
设计购物车数据模式
─────────────────────────────────────────
What: Create database schema for cart and cart_items tables
做什么：为 cart 和 cart_items 表创建数据库模式

Output:
- Cart table (id, user_id, session_id, created_at, updated_at)
- CartItem table (id, cart_id, product_id, quantity, price_snapshot)

Depends on: Nothing (foundation layer)
依赖：无（基础层）
```

```
Step 2: Create Cart API Endpoints
创建购物车 API 端点
─────────────────────────────────────────
What: Build REST endpoints for cart operations
做什么：构建购物车操作的 REST 端点

Output:
- GET    /api/cart           - Get current cart
- POST   /api/cart/items     - Add item to cart
- PATCH  /api/cart/items/:id - Update quantity
- DELETE /api/cart/items/:id - Remove item
- DELETE /api/cart           - Clear cart

Depends on: Step 1 (needs schema)
依赖：步骤1（需要数据模式）
```

```
Step 3: Implement Cart Service/Business Logic
实现购物车服务/业务逻辑
─────────────────────────────────────────
What: Create service layer with cart logic
做什么：创建包含购物车逻辑的服务层

Output:
- CartService class with methods
- Stock validation before adding
- Price calculation with discounts
- Cart merging (guest → logged in user)

Depends on: Step 1, Step 2
依赖：步骤1、步骤2
```

```
Step 4: Create Cart State Management (Frontend)
创建购物车状态管理（前端）
─────────────────────────────────────────
What: Set up frontend state for cart data
做什么：为购物车数据设置前端状态

Output:
- Cart store/context (items, total, count)
- Actions: addItem, removeItem, updateQuantity, clearCart
- Sync with API endpoints
- Persist to localStorage for guests

Depends on: Step 2 (needs API contract)
依赖：步骤2（需要 API 契约）
```

```
Step 5: Build Cart UI Components
构建购物车 UI 组件
─────────────────────────────────────────
What: Create React components for cart display
做什么：创建用于显示购物车的 React 组件

Output:
- CartIcon (header, shows item count)
- CartDrawer/CartPage (full cart view)
- CartItem (single item row)
- CartSummary (subtotal, taxes, total)
- EmptyCart (empty state)

Depends on: Step 4 (needs state management)
依赖：步骤4（需要状态管理）
```

```
Step 6: Add "Add to Cart" to Product Pages
在产品页面添加"加入购物车"
─────────────────────────────────────────
What: Integrate cart functionality into existing product UI
做什么：将购物车功能集成到现有产品 UI

Output:
- AddToCartButton component
- Quantity selector
- Success feedback (toast/animation)
- Handle out-of-stock states

Depends on: Step 4, Step 5
依赖：步骤4、步骤5
```

```
Step 7: Testing & Edge Cases
测试与边界情况
─────────────────────────────────────────
What: Write tests and handle edge cases
做什么：编写测试并处理边界情况

Output:
- Unit tests for CartService
- Integration tests for API endpoints
- E2E test for add-to-cart flow
- Handle: stock changes, price changes, deleted products

Depends on: Steps 1-6 (all features complete)
依赖：步骤1-6（所有功能完成）
```

---

#### Visual Dependency Map / 可视化依赖图

```
Step 1: Schema
    │
    ▼
Step 2: API ──────────────┐
    │                     │
    ▼                     ▼
Step 3: Service      Step 4: State
    │                     │
    │                     ▼
    │                Step 5: UI
    │                     │
    └──────────┬──────────┘
               ▼
         Step 6: Integration
               │
               ▼
         Step 7: Testing
```

---

#### Key Principles Demonstrated / 展示的关键原则

| Principle | 原则 | Example | 示例 |
|-----------|------|---------|------|
| **Foundation first** | 基础优先 | Schema before API | 先模式后API |
| **Backend before frontend** | 后端先于前端 | API before State | 先API后状态 |
| **Data before UI** | 数据先于UI | State before Components | 先状态后组件 |
| **Core before integration** | 核心先于集成 | Cart page before product page | 先购物车页后产品页 |
| **Features before testing** | 功能先于测试 | All features then comprehensive tests | 所有功能后全面测试 |

---

### Exercise 2.2: Identify Dependencies / 识别依赖关系

**Task / 任务:** Identify dependencies for blog system features
识别博客系统功能的依赖关系

**Given Tasks / 给定任务:**
```
A. Create Post database model
B. Build post editor component (frontend)
C. Create GET /api/posts endpoint
D. Create POST /api/posts endpoint
E. Build post list page (frontend)
F. Add image upload to editor
G. Create Comment model and API
```

---

#### Dependency Analysis / 依赖分析

```
A. Create Post database model          → Foundation (no dependencies)
B. Build post editor component         → Needs D (API to submit to)
C. Create GET /api/posts endpoint      → Needs A (Post model)
D. Create POST /api/posts endpoint     → Needs A (Post model)
E. Build post list page                → Needs C (API to fetch from)
F. Add image upload to editor          → Needs B (editor must exist)
G. Create Comment model and API        → Needs A (links to Post)
```

---

#### Parallel Groups / 可并行组

```
Layer 1 (Foundation / 基础层):
┌─────────────────────────────────────┐
│  A. Post database model             │  ← Must be FIRST
└─────────────────────────────────────┘

Layer 2 (Can run in PARALLEL / 可并行):
┌─────────────────┬─────────────────┬─────────────────┐
│ C. GET /posts   │ D. POST /posts  │ G. Comment API  │
└─────────────────┴─────────────────┴─────────────────┘
     All depend on A, but independent of each other

Layer 3 (Can run in PARALLEL / 可并行):
┌─────────────────┬─────────────────┐
│ E. Post list    │ B. Post editor  │
│   (needs C)     │   (needs D)     │
└─────────────────┴─────────────────┘

Layer 4 (Final / 最终层):
┌─────────────────────────────────────┐
│  F. Image upload (needs B)          │
└─────────────────────────────────────┘
```

---

#### Dependency Diagram / 依赖关系图

```
                    ┌───────────────────┐
                    │ A. Post Model     │
                    │    文章模型        │
                    └─────────┬─────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ C. GET API  │     │ D. POST API │     │ G. Comments │
   │   获取API    │     │   提交API    │     │    评论     │
   └──────┬──────┘     └──────┬──────┘     └─────────────┘
          │                   │
          ▼                   ▼
   ┌─────────────┐     ┌─────────────┐
   │ E. List Page│     │ B. Editor   │
   │   列表页     │     │   编辑器    │
   └─────────────┘     └──────┬──────┘
                              │
                              ▼
                       ┌─────────────┐
                       │ F. Image    │
                       │   Upload    │
                       │   图片上传   │
                       └─────────────┘
```

---

#### Optimal Execution Order / 最优执行顺序

```
Phase 1:  A                          (sequential, foundation)
Phase 2:  C, D, G                    (parallel, all need only A)
Phase 3:  E, B                       (parallel, E needs C, B needs D)
Phase 4:  F                          (sequential, needs B)

Total: 4 phases instead of 7 sequential steps
总计：4个阶段，而非7个顺序步骤
```

---

#### Key Insight / 关键洞察

```
┌─────────────────────────────────────────────────────────────┐
│  IDENTIFY PARALLELISM = FASTER DEVELOPMENT                  │
│  识别并行性 = 更快的开发                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Sequential: A → C → D → G → E → B → F  = 7 rounds         │
│  顺序执行：7轮                                               │
│                                                             │
│  Optimized:  A → [C,D,G] → [E,B] → F    = 4 rounds         │
│  优化后：4轮                                                 │
│                                                             │
│  Time saved: ~43%                                           │
│  节省时间：约43%                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Exercise 2.3: Write Chained Prompts / 编写链式提示词

**Task / 任务:** Write 3 sequential prompts for file upload feature
为文件上传功能编写3个顺序提示词

**Context / 上下文:**
- React + Node.js + Express app
- Files uploaded to AWS S3
- Support images and PDFs, max 10MB
- Show upload progress

---

#### Prompt 1: Backend Setup / 后端设置

```
Create a file upload API endpoint with S3 integration.
创建带有 S3 集成的文件上传 API 端点。

## Context / 上下文
- Express.js backend in src/server/
- AWS SDK already installed, credentials in .env
- Follow patterns in src/server/controllers/

## Requirements / 需求

### 1. S3 Service (src/server/services/s3Service.ts)
Create a service class with methods:
- uploadFile(file: Buffer, filename: string, mimetype: string): Promise<string>
  → Returns the S3 URL
- deleteFile(fileKey: string): Promise<void>
- generateSignedUrl(fileKey: string, expiresIn: number): Promise<string>

### 2. Upload Controller (src/server/controllers/uploadController.ts)
- POST /api/upload endpoint
- Use multer for multipart handling
- Validate: images (jpg, png, gif, webp) and PDFs only
- Max file size: 10MB
- Return: { url: string, key: string, filename: string, size: number }

### 3. Validation & Errors
- Invalid file type → 400 "File type not allowed. Supported: jpg, png, gif, webp, pdf"
- File too large → 400 "File exceeds 10MB limit"
- S3 failure → 500 "Upload failed, please try again"

## S3 Config / S3 配置
- Bucket: process.env.AWS_S3_BUCKET
- Region: process.env.AWS_REGION
- Use UUID + original extension for file keys

## Output / 输出
After this step, I should be able to test with:
curl -X POST -F "file=@test.jpg" http://localhost:3000/api/upload
```

**Produces for next step / 为下一步产出:**
- `POST /api/upload` endpoint
- Response format: `{ url, key, filename, size }`
- Error response format

---

#### Prompt 2: Frontend Upload Component / 前端上传组件

```
Create a reusable FileUpload React component with progress tracking.
创建一个带有进度跟踪的可复用 FileUpload React 组件。

## Context / 上下文
- React 18 + TypeScript in src/client/
- Using the POST /api/upload endpoint from previous step
- Existing UI components in src/client/components/ui/

## Component: FileUpload (src/client/components/FileUpload/index.tsx)

### Props Interface / 属性接口
interface FileUploadProps {
  onUploadComplete: (result: UploadResult) => void;
  onError?: (error: string) => void;
  accept?: string[];           // Default: ['image/*', 'application/pdf']
  maxSizeMB?: number;          // Default: 10
  disabled?: boolean;
}

interface UploadResult {
  url: string;
  key: string;
  filename: string;
  size: number;
}

### Features / 功能
1. Drag & drop zone with visual feedback
   拖放区域带视觉反馈

2. Click to open file picker
   点击打开文件选择器

3. Client-side validation BEFORE upload
   上传前的客户端验证
   - File type check / 文件类型检查
   - File size check / 文件大小检查

4. Upload progress bar (0-100%)
   上传进度条（0-100%）

5. States: idle, dragging, uploading, success, error
   状态：空闲、拖拽中、上传中、成功、错误

### UI States / UI 状态
- Idle: Dashed border, upload icon, "Drag file here or click to browse"
- Dragging: Highlighted border, "Drop file here"
- Uploading: Progress bar, filename, percentage, cancel button
- Success: Checkmark, filename, file size
- Error: Red border, error message, "Try again" button

### Use XMLHttpRequest for progress tracking / 使用 XMLHttpRequest 跟踪进度
(fetch doesn't support upload progress)

## File Structure / 文件结构
src/client/components/FileUpload/
├── index.tsx        # Main component
├── FileUpload.css   # Styles
└── types.ts         # TypeScript interfaces

## Test Usage / 测试用法
<FileUpload
  onUploadComplete={(result) => console.log('Uploaded:', result)}
  onError={(err) => console.error(err)}
/>
```

**Produces for next step / 为下一步产出:**
- Reusable `<FileUpload />` component
- Typed props and callbacks
- All UI states handled

---

#### Prompt 3: Integration & Polish / 集成与完善

```
Integrate FileUpload into the post editor and add finishing touches.
将 FileUpload 集成到文章编辑器并添加完善功能。

## Context / 上下文
- FileUpload component created in src/client/components/FileUpload/
- Post editor at src/client/pages/PostEditor.tsx
- Backend upload API at POST /api/upload

## Task 1: Integrate into Post Editor / 集成到文章编辑器

In src/client/pages/PostEditor.tsx:
- Add FileUpload component below the content textarea
- When upload completes, insert markdown image/link into content:
  - Images: ![filename](url)
  - PDFs: [filename](url)
- Store uploaded file keys in form state for cleanup if post is discarded

## Task 2: Add Multiple File Support / 添加多文件支持

Enhance the integration to show:
- List of uploaded files with thumbnails (images) or icons (PDFs)
- Remove button for each uploaded file
- Call DELETE /api/upload/:key when removing

## Task 3: Error Handling & UX Polish / 错误处理与用户体验完善

Add these finishing touches:
1. Toast notification on successful upload
   上传成功时的 Toast 通知

2. Retry mechanism: if upload fails, keep file and show "Retry" button
   重试机制：如果上传失败，保留文件并显示"重试"按钮

3. Keyboard accessibility: Enter/Space to trigger file picker
   键盘可访问性：Enter/Space 触发文件选择器

4. Loading state: disable form submit while upload in progress
   加载状态：上传进行中时禁用表单提交

## Task 4: Cleanup on Unmount / 卸载时清理

If user leaves the page with uploaded files but doesn't save the post:
如果用户离开页面但未保存文章：
- Show confirmation dialog: "You have uploaded files. Discard them?"
- If confirmed, call delete API for each uploaded file key

## Verification Checklist / 验证清单
After implementation, verify:
- [ ] Can drag & drop image → appears in editor preview
- [ ] Can drag & drop PDF → link inserted in content
- [ ] Progress bar shows during upload
- [ ] Can remove uploaded file
- [ ] Error shown for file > 10MB
- [ ] Error shown for invalid file type (.exe, etc.)
- [ ] Upload works on mobile (tap to select)
```

---

#### Chain Summary / 链式总结

```
┌─────────────────────────────────────────────────────────────┐
│                    PROMPT CHAIN FLOW                        │
│                      提示词链流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Prompt 1: BACKEND                                          │
│  ┌─────────────────────┐                                   │
│  │ • S3 Service        │                                   │
│  │ • Upload endpoint   │──┐                                │
│  │ • Validation        │  │                                │
│  └─────────────────────┘  │                                │
│                           │ Produces: API contract         │
│                           ▼                                │
│  Prompt 2: FRONTEND COMPONENT                              │
│  ┌─────────────────────┐                                   │
│  │ • FileUpload UI     │                                   │
│  │ • Progress tracking │──┐                                │
│  │ • State management  │  │                                │
│  └─────────────────────┘  │                                │
│                           │ Produces: Reusable component   │
│                           ▼                                │
│  Prompt 3: INTEGRATION                                     │
│  ┌─────────────────────┐                                   │
│  │ • Editor integration│                                   │
│  │ • Multi-file support│                                   │
│  │ • Polish & cleanup  │                                   │
│  └─────────────────────┘                                   │
│            │                                               │
│            ▼                                               │
│     ✅ COMPLETE FEATURE                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Day 2 Key Takeaways / 第二天关键收获

```
┌─────────────────────────────────────────────────────────────┐
│              TASK DECOMPOSITION PRINCIPLES                  │
│                    任务分解原则                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. FOUNDATION FIRST / 基础优先                             │
│     Database → API → Frontend → Integration                 │
│                                                             │
│  2. IDENTIFY PARALLELISM / 识别并行性                        │
│     Independent tasks can run together                      │
│     独立任务可以一起运行                                      │
│                                                             │
│  3. EACH STEP PRODUCES SOMETHING / 每步产出东西              │
│     Testable output before moving on                        │
│     继续前有可测试的输出                                      │
│                                                             │
│  4. EXPLICIT DEPENDENCIES / 明确依赖                         │
│     "Using the API from step 1..."                          │
│     "使用步骤1的API..."                                      │
│                                                             │
│  5. VERIFY BEFORE CONTINUING / 继续前验证                    │
│     Include test/verification in each prompt                │
│     每个提示词包含测试/验证                                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Reference / 快速参考

### Decomposition Checklist / 分解检查清单

Before starting a complex task:
开始复杂任务之前：

```
□ Can this be broken into smaller pieces?
  这能分解成更小的部分吗？

□ What is the foundation that must come first?
  什么是必须先完成的基础？

□ What are the dependencies between pieces?
  各部分之间的依赖是什么？

□ Which pieces can run in parallel?
  哪些部分可以并行？

□ How will I verify each step before moving on?
  如何在继续前验证每个步骤？

□ What does each step produce for the next?
  每个步骤为下一步产出什么？
```

### Common Decomposition Patterns / 常见分解模式

```
FULL-STACK FEATURE:
Schema → API → Service → State → UI → Integration → Tests

REFACTORING:
Analyze → Plan → Extract → Rename → Reorganize → Verify

BUG FIX (complex):
Reproduce → Isolate → Root cause → Fix → Test → Regression check

NEW INTEGRATION:
Research → Prototype → Core impl → Error handling → Polish
```

---

## Homework / 作业 (Optional)

Take a feature you need to build and:
拿一个你需要构建的功能：

1. **List all subtasks** (aim for 5-10)
   列出所有子任务（目标5-10个）

2. **Draw dependency graph**
   绘制依赖关系图

3. **Identify parallel groups**
   识别可并行组

4. **Write first 2 prompts in the chain**
   编写链中的前2个提示词

---

**Next: Day 3 - Context & Constraints / 下一课：第三天 - 上下文与约束**
